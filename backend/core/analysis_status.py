"""
backend/core/analysis_status.py
=================================
O-120: gemeinsamer Helfer, der `SourceScanFile.parse_status`/`parse_error`
(geschrieben von `GitConnector`, siehe parser/connectors/git.py und
parser/core/model.py::classify_completeness) für eine Menge von
(source_id, file_path)-Paaren nachschlägt — verwendet von den drei Stellen,
die O-120 ausdrücklich als Durchreich-Ziele nennt: Editor-Dateibaum
(api/knowledge_sources.py), Call-Graph (api/callgraph.py) und Chat-Zitate
(api/chat.py). Eine Stelle statt drei Kopien derselben Batch-Query.

Liefert absichtlich NUR Einträge für Dateien, deren Analyse nicht
uneingeschränkt vollständig ist (`parse_status` gesetzt und != "complete") —
die überwiegende Mehrheit der Dateien braucht in keiner der drei Antworten
ein zusätzliches Feld, und ein fehlender Eintrag ist für die Aufrufer schon
"kein Makel bekannt" (genau wie `parse_status IS NULL` das für Dateien ohne
Strukturparser-Beteiligung immer schon war).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.database import SourceScanFile


def load_analysis_status(
    db: Session, keys: set[tuple[int | None, str | None]]
) -> dict[tuple[int, str], dict]:
    """`keys` ist eine Menge aus (source_id, file_path) -- typischerweise aus
    den gerade gebauten Antwort-Objekten selbst zusammengestellt (Chat-
    Quellen, Callgraph-Knoten, Projekt-Entities). Fehlende/None-Werte werden
    ignoriert statt einen Query-Fehler zu riskieren -- nicht jede Quelle
    (Confluence/Jira/lokaler Upload) hat übrigens jemals SourceScanFile-Zeilen
    mit gesetztem parse_status (nur GitConnector schreibt COBOL-Strukturstatus,
    siehe core/model.py-Kommentar dort), das ist kein Fehlerfall.
    """
    pairs = {(source_id, file_path) for source_id, file_path in keys if source_id and file_path}
    if not pairs:
        return {}
    source_ids = {source_id for source_id, _ in pairs}
    rows = db.query(SourceScanFile).filter(SourceScanFile.source_id.in_(source_ids)).all()
    result: dict[tuple[int, str], dict] = {}
    for row in rows:
        key = (row.source_id, row.file_path)
        if key not in pairs:
            continue
        if not row.parse_status or row.parse_status == "complete":
            continue
        result[key] = {
            "status": row.parse_status,
            "reasons": row.parse_error.split("; ") if row.parse_error else [],
        }
    return result
