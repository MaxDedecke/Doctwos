"""Code-Beziehungen der Graph-Übersicht als Datei-Graph mit Grundgerüst.

Der Server bildet die Dateikanten aus allen Parser-Beziehungen in einer Abfrage. Ab
`BACKBONE_MIN_FILE_EDGES` Dateikanten zeigt die Übersicht nur das Grundgerüst: je Datei die
`BACKBONE_EDGES_PER_NODE` gewichtigsten Kanten, dazu von jeder Beziehungsart mindestens
`BACKBONE_MIN_PER_EDGE_TYPE` Vertreter. So erscheint jede vernetzte Datei, während die übrigen
Kanten als nicht geladene Verbindungen (`degree`) im Frontend nachgeladen werden können.

Gewicht einer Dateikante: zuerst die stärkste enthaltene Beziehungsrolle laut `LanguageProfile`
(Kontrollfluss und Einbindung, dann Datennutzung, dann sonstige, zuletzt reine Imports), danach die
Zahl der Einzelbeziehungen.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.language_profile import CONTROL_EDGES, DATA_EDGES, INCLUDE_EDGES, NAMING_EDGES

BACKBONE_MIN_FILE_EDGES = 1000
BACKBONE_EDGES_PER_NODE = 3
BACKBONE_MIN_PER_EDGE_TYPE = 3
# Bis zu so viele Einzelbeziehungen je Dateikante dienen als Belegstellen.
SAMPLE_EDGES_PER_PAIR = 5

FileKey = tuple[Optional[int], Optional[int], str]


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


# Projekt- und Quell-IDs ohne Wert werden zu 0 (IDs beginnen bei 1): Gleichheit statt
# IS NOT DISTINCT FROM erlaubt Hash-Joins, sonst braucht die Abfrage bei Syncope das Siebenfache.
_QUERY = """
WITH raw AS (
    SELECT coalesce(s.project_id, 0) AS sp, coalesce(s.source_id, 0) AS ss, s.file_path AS sf,
           coalesce(d.project_id, 0) AS dp, coalesce(d.source_id, 0) AS ds, d.file_path AS df,
           e.id, e.type
    FROM code_edges e
    JOIN code_entities s ON s.id = e.src_entity_id
    JOIN code_entities d ON d.id = e.dst_entity_id
    WHERE {scope}
),
pairs AS (
    SELECT row_number() OVER () AS pid, sp, ss, sf, dp, ds, df,
           count(*) AS edge_count,
           array_agg(DISTINCT type) AS types,
           (array_agg(id ORDER BY id))[1:{samples}] AS sample_ids,
           max(CASE WHEN type = ANY(:strong) THEN 3
                    WHEN type = ANY(:data) THEN 2
                    WHEN type = ANY(:naming) THEN 0
                    ELSE 1 END) AS priority
    FROM raw
    WHERE NOT (sf = df AND ss = ds AND sp = dp)
    GROUP BY sp, ss, sf, dp, ds, df
),
ends AS (
    SELECT pid, sp AS np, ss AS ns, sf AS nf, priority, edge_count FROM pairs
    UNION ALL
    SELECT pid, dp, ds, df, priority, edge_count FROM pairs
),
node_degree AS (
    SELECT np, ns, nf, count(*) AS degree FROM ends GROUP BY np, ns, nf
),
per_node AS (
    SELECT pid FROM (
        SELECT pid, row_number() OVER (
            PARTITION BY np, ns, nf ORDER BY priority DESC, edge_count DESC, pid) AS r
        FROM ends) ranked
    WHERE r <= :per_node
),
per_type AS (
    SELECT pid FROM (
        SELECT pid, row_number() OVER (
            PARTITION BY t ORDER BY priority DESC, edge_count DESC, pid) AS r
        FROM pairs, unnest(types) AS t) ranked
    WHERE r <= :per_type
),
kept AS (SELECT pid FROM per_node UNION SELECT pid FROM per_type),
total AS (SELECT count(*) AS n FROM pairs)
SELECT p.sp, p.ss, p.sf, p.dp, p.ds, p.df, p.edge_count, p.types, p.sample_ids,
       sd.degree AS source_degree, td.degree AS target_degree, total.n AS total_pairs
FROM pairs p
CROSS JOIN total
LEFT JOIN kept k ON k.pid = p.pid
JOIN node_degree sd ON sd.np = p.sp AND sd.ns = p.ss AND sd.nf = p.sf
JOIN node_degree td ON td.np = p.dp AND td.ns = p.ds AND td.nf = p.df
WHERE total.n <= :min_file_edges OR k.pid IS NOT NULL
ORDER BY p.priority DESC, p.edge_count DESC, p.pid
LIMIT :max_pairs
"""


def load_code_file_graph(
    db: Session,
    project_id: Optional[int],
    exposed_project_ids: list[int],
    file_id: Callable[[Optional[int], Optional[int], str], str],
    max_pairs: int,
) -> CodeFileGraph:
    params: dict = {
        "strong": sorted(CONTROL_EDGES | (INCLUDE_EDGES - NAMING_EDGES)),
        "data": sorted(DATA_EDGES),
        "naming": sorted(NAMING_EDGES),
        "per_node": BACKBONE_EDGES_PER_NODE,
        "per_type": BACKBONE_MIN_PER_EDGE_TYPE,
        "min_file_edges": BACKBONE_MIN_FILE_EDGES,
        # Eine Zeile mehr zeigt an, dass der Deckel gegriffen hat.
        "max_pairs": max_pairs + 1,
    }
    if project_id:
        scope = "e.project_id = :project_id"
        params["project_id"] = project_id
    elif exposed_project_ids:
        scope = "(e.project_id = ANY(:project_ids) OR e.project_id IS NULL)"
        params["project_ids"] = list(exposed_project_ids)
    else:
        scope = "e.project_id IS NULL"
    rows = db.execute(text(_QUERY.format(scope=scope, samples=SAMPLE_EDGES_PER_PAIR)), params).all()

    graph = CodeFileGraph(pairs=[], capped=len(rows) > max_pairs)
    for row in rows[:max_pairs]:
        source: FileKey = (row.sp or None, row.ss or None, row.sf)
        target: FileKey = (row.dp or None, row.ds or None, row.df)
        graph.pairs.append(
            FilePair(source, target, row.edge_count, sorted(row.types), list(row.sample_ids))
        )
        graph.degree[file_id(*source)] = row.source_degree
        graph.degree[file_id(*target)] = row.target_degree
        graph.total_pairs = row.total_pairs
    graph.backbone = graph.capped or graph.total_pairs > len(graph.pairs)
    return graph
