"""
backend/services/source_tree.py
===============================
Datei-Baum einer Wissensquelle, ebenenweise und seitenweise: Eine Anfrage liefert nur die direkten Einträge
eines Ordners (Unterordner mit Anzahl, Dateien mit Analysestatus), höchstens ``limit`` auf einmal.

Große Quellen (Camel: >40.000 Dateien, Jira: Tausende Issues ohne Ordner) laden so beim Aufklappen nur, was
sichtbar wird. Pfade stammen aus dem Scanprotokoll (auch übersprungene Dateien) oder, ohne Scan, aus den Chunks (ohne
``#``-Abschnittsteil).
"""

from collections import Counter, defaultdict
from typing import Optional

from sqlalchemy import Integer, Numeric, and_, cast, func, literal, select
from sqlalchemy.orm import Session

from core.scan_report import summarize_edges, summarize_scan_reasons
from doctus_models.database import DocumentChunk, SourceScanFile

MAX_PAGE = 500


def _like_prefix(prefix: str) -> str:
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}%"


def list_directory(db: Session, source_id: int, directory: str, *, offset: int, limit: int) -> dict:
    """Direkte Einträge von ``directory`` (leer = Wurzel): Ordner zuerst, dann Dateien, je alphabetisch."""
    directory = directory.strip("/")
    prefix = f"{directory}/" if directory else ""
    like = _like_prefix(prefix)
    # Nach einem Import ist das Scanprotokoll maßgeblich und deutlich kleiner als die Chunks (Camel: 44.000
    # Einträge statt 720.000 Chunks). Quellen ohne Scan (Jira, Confluence, Uploads) kennen nur ihre Chunks.
    has_scan = db.query(SourceScanFile.id).filter(SourceScanFile.source_id == source_id).first()
    if has_scan:
        paths = (
            select(SourceScanFile.file_path.label("path"))
            .where(
                SourceScanFile.source_id == source_id,
                SourceScanFile.file_path.like(like, escape="\\"),
            )
            .distinct()
            .subquery()
        )
    else:
        paths = (
            select(func.split_part(DocumentChunk.file_path, "#", 1).label("path"))
            .where(
                DocumentChunk.source_id == source_id,
                DocumentChunk.file_path.like(like, escape="\\"),
            )
            .distinct()
            .subquery()
        )
    rest = func.substr(paths.c.path, len(prefix) + 1)
    is_dir = cast(func.strpos(rest, "/") > 0, Integer)
    name = func.split_part(rest, "/", 1)
    entries = (
        select(name.label("name"), is_dir.label("is_dir"), func.count().label("files"))
        .where(and_(rest != literal(""), paths.c.path.isnot(None)))
        .group_by(name, is_dir)
        .subquery()
    )
    rows = db.execute(
        select(
            entries.c.name,
            entries.c.is_dir,
            entries.c.files,
            func.count().over().label("total"),
        )
        .order_by(
            entries.c.is_dir.desc(),
            # Natürliche Reihenfolge für Nummern am Ende (SYNCOPE-2 vor SYNCOPE-10, Issue 9 vor 10).
            func.lower(func.regexp_replace(entries.c.name, "[0-9]+$", "")),
            cast(func.nullif(func.substring(entries.c.name, "[0-9]+$"), ""), Numeric).nulls_first(),
            entries.c.name,
        )
        .offset(offset)
        .limit(limit)
    ).all()
    total = rows[0].total if rows else 0
    if not rows and offset:
        total = db.execute(select(func.count()).select_from(entries)).scalar() or 0

    file_paths = [f"{prefix}{row.name}" for row in rows if not row.is_dir]
    status = _file_status(db, source_id, file_paths)
    items = []
    for row in rows:
        path = f"{prefix}{row.name}"
        if row.is_dir:
            items.append({"type": "dir", "name": row.name, "path": path, "files": row.files})
        else:
            items.append(
                {
                    "type": "file",
                    "name": row.name,
                    "path": path,
                    **({"status": status[path]} if path in status else {}),
                }
            )
    next_offset: Optional[int] = offset + len(rows) if offset + len(rows) < total else None
    return {"dir": directory, "entries": items, "total": total, "next_offset": next_offset}


def _file_status(db: Session, source_id: int, paths: list[str]) -> dict[str, dict]:
    """Analysestatus der Dateien, die nicht uneingeschränkt analysiert sind (O-120)."""
    if not paths:
        return {}
    rows = db.query(
        SourceScanFile.file_path,
        SourceScanFile.parse_status,
        SourceScanFile.parse_error,
        SourceScanFile.language,
        SourceScanFile.encoding,
    ).filter(
        SourceScanFile.source_id == source_id,
        SourceScanFile.file_path.in_(paths),
        SourceScanFile.parse_status.isnot(None),
        SourceScanFile.parse_status != "complete",
    )
    status = {}
    for path, parse_status, error, language, encoding in rows:
        details = {"status": parse_status, "reasons": error.split("; ") if error else []}
        if language:
            details["language"] = language
        if encoding:
            details["encoding"] = encoding
        status[path] = details
    return status


def scan_summary(db: Session, source_id: int) -> dict:
    """Zusammenfassung des letzten Scans: Status, Kodierungen, Sprachen, Gründe und Kantenlage."""
    scan_rows = (
        db.query(
            SourceScanFile.language,
            SourceScanFile.parse_status,
            SourceScanFile.parse_error,
            SourceScanFile.encoding,
        )
        .filter(SourceScanFile.source_id == source_id)
        .all()
    )
    by_language: dict[str, Counter] = defaultdict(Counter)
    by_status: Counter = Counter()
    by_encoding: Counter = Counter()
    for language, status, _error, encoding in scan_rows:
        language = language or "unknown"
        status = status or "unreported"
        by_language[language][status] += 1
        by_status[status] += 1
        if encoding:
            by_encoding[encoding] += 1
    return {
        **summarize_scan_reasons([(row[0], row[1], row[2]) for row in scan_rows]),
        "edges": summarize_edges(db, source_id),
        "total_files": len(scan_rows),
        "by_status": dict(sorted(by_status.items())),
        "by_encoding": dict(sorted(by_encoding.items())),
        "by_language": {
            language: {
                "total_files": sum(statuses.values()),
                "by_status": dict(sorted(statuses.items())),
            }
            for language, statuses in sorted(by_language.items())
        },
    }
