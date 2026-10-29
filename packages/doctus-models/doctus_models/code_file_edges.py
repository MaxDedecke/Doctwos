"""Code-Beziehungen zu Dateikanten zusammenfassen und das Grundgerüst der Graph-Übersicht bestimmen.

Eine Dateikante fasst alle Parser-Beziehungen zwischen zwei Dateien zusammen. Ab
`BACKBONE_MIN_FILE_EDGES` Dateikanten gehört eine Kante nur zum Grundgerüst, wenn sie für Quell-
oder Zieldatei unter deren `BACKBONE_EDGES_PER_NODE` gewichtigsten ist oder zu den
`BACKBONE_MIN_PER_EDGE_TYPE` gewichtigsten einer Beziehungsart gehört. So erscheint jede vernetzte
Datei; die übrigen Kanten bleiben über den Grad als nicht geladen erkennbar.

Gewicht: zuerst die stärkste enthaltene Rolle laut `language_profile` (Kontrollfluss und
Einbindung, dann Datennutzung, dann sonstige, zuletzt reine Imports), danach die Zahl der
Einzelbeziehungen.

Der Parser schreibt am Ende jedes Syncs je Projekt das Grundgerüst in `code_file_edges`
(`rebuild_code_file_edges`); nur das liest die Übersicht. Dieselbe Abfrage dient dem Backend als
Rückfall, solange für ein Projekt noch nichts berechnet ist.
"""

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from doctus_models.language_profile import CONTROL_EDGES, DATA_EDGES, INCLUDE_EDGES, NAMING_EDGES

BACKBONE_MIN_FILE_EDGES = 1000
BACKBONE_EDGES_PER_NODE = 3
BACKBONE_MIN_PER_EDGE_TYPE = 3
# Bis zu so viele Einzelbeziehungen je Dateikante dienen als Belegstellen.
SAMPLE_EDGES_PER_PAIR = 5

# Projekt- und Quell-IDs ohne Wert werden zu 0 (IDs beginnen bei 1): Gleichheit statt
# IS NOT DISTINCT FROM erlaubt Hash-Joins, sonst braucht die Abfrage ein Vielfaches.
_FILE_EDGES = """
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
SELECT nullif(p.sp, 0) AS src_project_id, nullif(p.ss, 0) AS src_source_id,
       p.sf AS src_file_path,
       nullif(p.dp, 0) AS dst_project_id, nullif(p.ds, 0) AS dst_source_id,
       p.df AS dst_file_path,
       p.edge_count, to_json(p.types) AS edge_types, to_json(p.sample_ids) AS sample_edge_ids,
       p.priority, sd.degree AS src_degree, td.degree AS dst_degree,
       (total.n <= :min_file_edges OR k.pid IS NOT NULL) AS in_backbone, total.n AS total_pairs
FROM pairs p
CROSS JOIN total
LEFT JOIN kept k ON k.pid = p.pid
JOIN node_degree sd ON sd.np = p.sp AND sd.ns = p.ss AND sd.nf = p.sf
JOIN node_degree td ON td.np = p.dp AND td.ns = p.ds AND td.nf = p.df
"""

_COLUMNS = (
    "src_project_id, src_source_id, src_file_path, dst_project_id, dst_source_id, dst_file_path, "
    "edge_count, edge_types, sample_edge_ids, priority, src_degree, dst_degree, total_pairs"
)


def _params() -> dict:
    return {
        "strong": sorted(CONTROL_EDGES | (INCLUDE_EDGES - NAMING_EDGES)),
        "data": sorted(DATA_EDGES),
        "naming": sorted(NAMING_EDGES),
        "per_node": BACKBONE_EDGES_PER_NODE,
        "per_type": BACKBONE_MIN_PER_EDGE_TYPE,
        "min_file_edges": BACKBONE_MIN_FILE_EDGES,
    }


def file_edges_query(scope: str) -> str:
    """Alle Dateikanten im Bereich `scope` (SQL-Bedingung über `e`, den code_edges-Alias)."""
    return _FILE_EDGES.format(scope=scope, samples=SAMPLE_EDGES_PER_PAIR)


def file_edges_params() -> dict:
    return _params()


def rebuild_code_file_edges(db: Session, project_id: Optional[int]) -> int:
    """Berechnet das Grundgerüst eines Projekts neu und gibt die Zahl seiner Dateikanten zurück.

    Löschen und Einfügen laufen in der Transaktion des Aufrufers; Leser sehen bis zum Commit den
    alten Stand. Die Sperre verhindert, dass zwei gleichzeitig endende Syncs eines Projekts ihre
    Zeilen doppelt einfügen.
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('code_file_edges'), :key)"),
        {"key": project_id or 0},
    )
    if project_id is None:
        db.execute(text("DELETE FROM code_file_edges WHERE project_id IS NULL"))
        scope, params = "e.project_id IS NULL", _params()
    else:
        db.execute(
            text("DELETE FROM code_file_edges WHERE project_id = :project_id"),
            {"project_id": project_id},
        )
        scope, params = "e.project_id = :project_id", {**_params(), "project_id": project_id}
    result = db.execute(
        text(
            f"INSERT INTO code_file_edges (project_id, {_COLUMNS}) "
            f"SELECT :scope_project_id, {_COLUMNS} FROM ({file_edges_query(scope)}) file_edges "
            "WHERE in_backbone"
        ),
        {**params, "scope_project_id": project_id},
    )
    return result.rowcount or 0
