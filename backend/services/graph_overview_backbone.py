"""Code-Beziehungen der Graph-Übersicht als Grundgerüst aus Dateikanten.

Das Grundgerüst berechnet der Parser am Ende jedes Syncs je Projekt vor (`code_file_edges`, siehe
`doctus_models.code_file_edges`); damit hängt die Ladezeit der Übersicht nicht mehr von der Zahl
der Parser-Beziehungen ab. Ist für den Bereich noch nichts
berechnet (vor dem ersten Sync nach dem Update), fasst sie die Beziehungen wie früher direkt zusammen.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from doctus_models.code_file_edges import file_edges_params, file_edges_query

FileKey = tuple[Optional[int], Optional[int], str]

_COLUMNS = (
    "src_project_id, src_source_id, src_file_path, dst_project_id, dst_source_id, dst_file_path, "
    "edge_count, edge_types, sample_edge_ids, src_degree, dst_degree"
)


@dataclass
class FilePair:
    source: FileKey
    target: FileKey
    edge_count: int
    edge_types: list[str]
    sample_edge_ids: list[int]


@dataclass
class CodeFileGraph:
    pairs: list[FilePair]
    # Dateikanten je Datei-Knoten im vollständigen Graphen, nicht nur unter den gelieferten.
    degree: dict[str, int] = field(default_factory=dict)
    total_pairs: int = 0
    backbone: bool = False
    capped: bool = False
    precomputed: bool = False


def _scope(column: str, project_id: Optional[int], exposed_project_ids: list[int]):
    if project_id:
        return f"{column} = :project_id", {"project_id": project_id}
    if exposed_project_ids:
        return (
            f"({column} = ANY(:project_ids) OR {column} IS NULL)",
            {"project_ids": list(exposed_project_ids)},
        )
    return f"{column} IS NULL", {}


def load_code_file_graph(
    db: Session,
    project_id: Optional[int],
    exposed_project_ids: list[int],
    file_id: Callable[[Optional[int], Optional[int], str], str],
    max_pairs: int,
) -> CodeFileGraph:
    # Eine Zeile mehr zeigt an, dass der Deckel gegriffen hat.
    limit = {"limit": max_pairs + 1}
    scope, params = _scope("project_id", project_id, exposed_project_ids)
    # Jede Zeile trägt die Gesamtzahl ihres Projekts; mehrere Projekte addieren sich.
    total = db.execute(
        text(
            "SELECT coalesce(sum(total_pairs), 0) FROM (SELECT DISTINCT ON (project_id) "
            f"total_pairs FROM code_file_edges WHERE {scope}) per_project"
        ),
        params,
    ).scalar_one()
    precomputed = bool(total)
    if precomputed:
        rows = db.execute(
            text(
                f"SELECT {_COLUMNS} FROM code_file_edges WHERE {scope} "
                "ORDER BY priority DESC, edge_count DESC, id LIMIT :limit"
            ),
            {**params, **limit},
        ).all()
    else:
        live_scope, live_params = _scope("e.project_id", project_id, exposed_project_ids)
        rows = db.execute(
            text(
                f"SELECT {_COLUMNS}, total_pairs FROM ({file_edges_query(live_scope)}) file_edges "
                "WHERE in_backbone ORDER BY priority DESC, edge_count DESC LIMIT :limit"
            ),
            {**file_edges_params(), **live_params, **limit},
        ).all()
        total = rows[0].total_pairs if rows else 0

    graph = CodeFileGraph(
        pairs=[], total_pairs=total, capped=len(rows) > max_pairs, precomputed=precomputed
    )
    for row in rows[:max_pairs]:
        source: FileKey = (row.src_project_id, row.src_source_id, row.src_file_path)
        target: FileKey = (row.dst_project_id, row.dst_source_id, row.dst_file_path)
        graph.pairs.append(
            FilePair(
                source, target, row.edge_count, sorted(row.edge_types), list(row.sample_edge_ids)
            )
        )
        graph.degree[file_id(*source)] = row.src_degree
        graph.degree[file_id(*target)] = row.dst_degree
    graph.backbone = graph.capped or graph.total_pairs > len(graph.pairs)
    return graph
