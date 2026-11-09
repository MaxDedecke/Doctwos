"""Analysestand einer Git-Quelle für den Chat-Agenten: Bestand je Sprache, unvollständig analysierte Dateien, Buildprofil.

Fragen wie „Welche Dateien sind nur teilweise analysiert?“ oder „Welches Buildprofil gilt?“ konnte der Agent nicht
beantworten; den Preflight gab es nur in den Einstellungen (Katalogtest 08.11.2026, C1/C11). Gezeigt wird derselbe
Bericht wie dort, ergänzt um begrenzte Dateilisten je Status mit ihrem Grund.
"""

from __future__ import annotations

from core.source_preflight import build_preflight
from doctus_models.database import SourceScanFile
from services.commit_diff import _source
from sqlalchemy.orm import Session

STATUSES = ("partial", "text_fallback", "skipped", "error")
MAX_FILES = 30


def source_status(
    db: Session,
    *,
    project_id: int,
    source_id: int | None = None,
    language: str | None = None,
    max_files: int = MAX_FILES,
) -> dict:
    source, error = _source(db, project_id, source_id)
    if error:
        return {"error": error}
    report = build_preflight(db, source)
    query = db.query(
        SourceScanFile.file_path,
        SourceScanFile.language,
        SourceScanFile.parse_status,
        SourceScanFile.parse_error,
    ).filter(SourceScanFile.source_id == source.id, SourceScanFile.parse_status.in_(STATUSES))
    if language:
        query = query.filter(SourceScanFile.language == language.lower())
    by_status: dict[str, dict] = {}
    for path, file_language, status, reason in query.order_by(SourceScanFile.file_path):
        bucket = by_status.setdefault(status, {"count": 0, "files": []})
        bucket["count"] += 1
        if len(bucket["files"]) < max_files:
            bucket["files"].append(
                {"path": path, "language": file_language, "reason": (reason or "")[:200] or None}
            )
    cursor = source.sync_cursor if isinstance(source.sync_cursor, dict) else {}
    profile = report["profile"]
    return {
        "status": "ok",
        "source_id": source.id,
        "source_name": source.name,
        "sync_status": source.sync_status,
        "indexed_commit": cursor.get("last_commit"),
        "build_profile": profile.get("build_profile")
        or "Kein Buildprofil gesetzt; Quellformat, Codepage und Compilerfamilie werden aus dem Inhalt erkannt.",
        "language_paths": profile.get("language_paths"),
        "files": report["files"],
        "incomplete_files": by_status,
        "parser_gaps": report["parser_gaps"][:8],
        "open_copybooks": {
            "ambiguous": [item["name"] for item in report["copybooks"]["ambiguous"]],
            "missing": [item["name"] for item in report["copybooks"]["missing"]],
        },
        "hints": [hint["message"] for hint in report["hints"]],
        "note": (
            "files.by_language zählt alle Dateien je Sprache und Status. incomplete_files listet höchstens "
            f"{max_files} Dateien je Status; count ist die volle Zahl."
        ),
    }
