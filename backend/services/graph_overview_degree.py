"""Echte Verbindungszahl je Übersichtsknoten.

Die Übersicht zeigt nur eine Auswahl der Kanten (Knotendeckel, Stichprobe der Code-Beziehungen).
Damit das Frontend nicht geladene Verbindungen anzeigen und gezielt nachladen kann, trägt jeder
gelieferte Knoten `degree`: die Zahl seiner Kanten im vollständigen Übersichtsgraphen.
"""

from collections import defaultdict
from typing import Callable, Optional

from sqlalchemy import and_, not_, or_
from sqlalchemy.orm import Session, aliased

from doctus_models.database import CodeEdge, CodeEntity
from services.graph_overview_sampling import compute_degree

CODE_FILE_EDGE_PREFIX = "code-files:"


def _exact_code_file_degrees(
    db: Session,
    project_id: Optional[int],
    exposed_project_ids: list[int],
    file_id: Callable[[Optional[int], Optional[int], str], str],
) -> dict[str, int]:
    """Zahl der Dateikanten je Datei, wie `_append_code_dependencies` sie aus allen Beziehungen bilden würde."""
    src, dst = aliased(CodeEntity), aliased(CodeEntity)
    query = (
        db.query(
            src.project_id,
            src.source_id,
            src.file_path,
            dst.project_id,
            dst.source_id,
            dst.file_path,
        )
        .select_from(CodeEdge)
        .join(src, src.id == CodeEdge.src_entity_id)
        .join(dst, dst.id == CodeEdge.dst_entity_id)
        .filter(
            not_(
                and_(
                    src.file_path == dst.file_path,
                    src.source_id.is_not_distinct_from(dst.source_id),
                    src.project_id.is_not_distinct_from(dst.project_id),
                )
            )
        )
    )
    if project_id:
        query = query.filter(CodeEdge.project_id == project_id)
    elif exposed_project_ids:
        query = query.filter(
            or_(CodeEdge.project_id.in_(exposed_project_ids), CodeEdge.project_id.is_(None))
        )
    else:
        query = query.filter(CodeEdge.project_id.is_(None))

    degree: dict[str, int] = defaultdict(int)
    for s_project, s_source, s_path, d_project, d_source, d_path in query.distinct():
        degree[file_id(s_project, s_source, s_path)] += 1
        degree[file_id(d_project, d_source, d_path)] += 1
    return degree


def overview_degrees(
    db: Session,
    nodes: dict[str, dict],
    edges: list[dict],
    *,
    code_edges_sampled: bool,
    project_id: Optional[int],
    exposed_project_ids: list[int],
    file_id: Callable[[Optional[int], Optional[int], str], str],
) -> dict[str, int]:
    degree = compute_degree(nodes, edges)
    if not code_edges_sampled:
        return degree
    # Nur die Code-Beziehungen sind eine Stichprobe; ihren Anteil durch die exakte Zählung ersetzen.
    sampled: dict[str, int] = defaultdict(int)
    for edge in edges:
        if edge["id"].startswith(CODE_FILE_EDGE_PREFIX):
            sampled[edge["source"]] += 1
            sampled[edge["target"]] += 1
    exact = _exact_code_file_degrees(db, project_id, exposed_project_ids, file_id)
    for node_id in degree:
        degree[node_id] += exact.get(node_id, 0) - sampled.get(node_id, 0)
    return degree
