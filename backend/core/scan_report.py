"""O-380: Gründe für nicht strukturiert indexierte Dateien und Kantenlage je Quelle.

Gruppiert `SourceScanFile.parse_error` in wenige, für Anwender lesbare Kategorien
und zählt unaufgelöste Kanten getrennt nach „extern“ (belegtes Systemziel, O-375/
O-377) und echter Lücke.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.database import CodeEdge

# Reihenfolge ist Priorität: der erste Treffer gewinnt.
_REASON_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("blocked_for_safety", ("aus Sicherheitsgründen",)),
    ("parser_error", (
        "Strukturparser fehlgeschlagen", "no viable alternative", "extraneous input",
        "mismatched input", "XML ist nicht gültig",
    )),
    ("no_structure_parser", ("hat keinen Strukturparser",)),
    ("uncovered_code", ("außerhalb erkannter Paragraphen",)),
    ("not_indexable", (
        "Binärformat", "leer (keine Textinhalte)", "kein UTF-8", "überschreitet",
        "Build-/IDE-Verzeichnis", "kein sinnvoller",
    )),
)
_PARSER_ERROR_CLASS = re.compile(r"Strukturparser fehlgeschlagen:\s*([A-Za-z_][\w.]*)")


def classify_reason(status: str | None, error: str | None) -> str:
    """Kategorie eines nicht vollständig analysierten Scan-Eintrags."""
    text = error or ""
    for category, markers in _REASON_CATEGORIES:
        if any(marker in text for marker in markers):
            return category
    return "not_indexable" if status == "skipped" else "other"


def summarize_scan_reasons(rows: list[tuple[str | None, str | None, str | None]]) -> dict:
    """`rows` sind (language, parse_status, parse_error); `complete` zählt nicht mit."""
    by_reason: dict[str, Counter] = defaultdict(Counter)
    parser_error_classes: Counter = Counter()
    for language, status, error in rows:
        if not status or status == "complete":
            continue
        by_reason[classify_reason(status, error)][language or "unknown"] += 1
        match = _PARSER_ERROR_CLASS.search(error or "")
        if match:
            parser_error_classes[match.group(1)] += 1
    return {
        "by_reason": {
            category: {"total_files": sum(langs.values()), "by_language": dict(sorted(langs.items()))}
            for category, langs in sorted(by_reason.items())
        },
        "parser_error_classes": dict(sorted(parser_error_classes.items())),
    }


def summarize_edges(db: Session, source_id: int) -> dict:
    """Kanten je Auflösungsstatus; unaufgelöste getrennt nach extern und offen."""
    by_resolution = dict(
        db.query(CodeEdge.resolution, func.count())
        .filter(CodeEdge.source_id == source_id)
        .group_by(CodeEdge.resolution)
        .all()
    )
    category = CodeEdge.meta_json["external"]["category"].as_string()
    external_by_category = dict(
        db.query(category, func.count())
        .filter(CodeEdge.source_id == source_id, CodeEdge.resolution == "unresolved", category.isnot(None))
        .group_by(category)
        .all()
    )
    unresolved = by_resolution.get("unresolved", 0)
    external = sum(external_by_category.values())
    return {
        "by_resolution": dict(sorted(by_resolution.items())),
        "unresolved_external": external,
        "unresolved_open": unresolved - external,
        "external_by_category": dict(sorted(external_by_category.items())),
    }
