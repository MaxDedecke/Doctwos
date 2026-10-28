"""Preflight-Bericht einer Git-Quelle für die Einrichtung beim Kunden (O-151).

Alles wird aus dem bereits Indexierten abgeleitet (Scan-Zeilen, Kanten), nichts wird neu
gelesen oder geparst. Der Bericht beantwortet: Was wurde wie gelesen, wo bricht die
Grammatik, welche COPY-Namen bleiben offen und welche Profilangaben fehlen.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource, SourceScanFile

STRUCTURED_LANGUAGES = ("cobol", "copybook", "jcl")
_TOP_GAPS = 15
_TOP_COPIES = 25
_MAX_TOKEN_CHARS = 40

# Teile von `SourceScanFile.parse_error` (Diagnosen sind mit "; " verbunden):
# "mismatched input 'GENERATE' expecting SECTION (insgesamt 3x, Zeilen: 18, 19)"
_GAP_PART = re.compile(
    r"^(?P<kind>mismatched input|no viable alternative at input|extraneous input|"
    r"token recognition error at:)\s*'(?P<token>.*?)'"
    r"(?:.*?\(insgesamt (?P<count>\d+)x, Zeilen: (?P<lines>[\d, ]+)\))?",
    re.S,
)


def _gap_key(kind: str, token: str) -> str:
    first = token.strip().split()[0] if token.strip() else ""
    return f"{kind} '{first[:_MAX_TOKEN_CHARS]}'"


def parser_gaps(rows: list[tuple[str, str | None, str | None]]) -> list[dict[str, Any]]:
    """Rangliste der häufigsten Grammatikfehler. `rows`: (Pfad, Status, parse_error)."""
    occurrences: Counter = Counter()
    files: dict[str, set[str]] = defaultdict(set)
    example: dict[str, tuple[str, int | None]] = {}
    for path, status, error in rows:
        if status not in ("partial", "text_fallback") or not error:
            continue
        for part in error.split("; "):
            match = _GAP_PART.match(part.strip())
            if not match:
                continue
            key = _gap_key(match["kind"], match["token"])
            count = int(match["count"]) if match["count"] else 1
            occurrences[key] += count
            files[key].add(path)
            if key not in example:
                lines = [int(n) for n in re.findall(r"\d+", match["lines"] or "")]
                example[key] = (path, lines[0] if lines else None)
    ranked = []
    for key, total in occurrences.most_common(_TOP_GAPS):
        path, line = example[key]
        ranked.append(
            {
                "pattern": key,
                "occurrences": total,
                "files": len(files[key]),
                "example": f"{path}:{line}" if line else path,
            }
        )
    return ranked


def _copybook_name(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0].upper()


def copy_resolution(db: Session, source_id: int, copybook_paths: list[str]) -> dict[str, Any]:
    """Offene COPY-Namen, getrennt in mehrdeutig (mehrere Kandidaten) und fehlend."""
    candidates: dict[str, list[str]] = defaultdict(list)
    for path in copybook_paths:
        candidates[_copybook_name(path)].append(path)

    external = CodeEdge.meta_json["external"]["category"].as_string()
    rows = (
        db.query(CodeEdge.dst_name, func.count(), func.min(CodeEntity.file_path))
        .join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id)
        .filter(
            CodeEdge.source_id == source_id,
            CodeEdge.type == "COPY",
            CodeEdge.resolution == "unresolved",
            external.is_(None),
        )
        .group_by(CodeEdge.dst_name)
        .order_by(func.count().desc(), CodeEdge.dst_name)
        .limit(_TOP_COPIES * 4)
        .all()
    )
    ambiguous, missing = [], []
    for name, count, first_file in rows:
        paths = candidates.get(os.path.splitext(name)[0].upper(), [])
        entry = {"name": name, "references": count, "example_file": first_file}
        if len(paths) > 1:
            ambiguous.append({**entry, "candidates": sorted(paths)[:10]})
        else:
            missing.append(entry)
    duplicates = sum(1 for paths in candidates.values() if len(paths) > 1)
    return {
        "ambiguous": ambiguous[:_TOP_COPIES],
        "missing": missing[:_TOP_COPIES],
        "duplicate_copybook_names": duplicates,
    }


def _spaces(source: KnowledgeSource) -> dict:
    spaces = source.spaces
    return spaces if isinstance(spaces, dict) else {}


def build_preflight(db: Session, source: KnowledgeSource) -> dict[str, Any]:
    scan_rows = (
        db.query(
            SourceScanFile.file_path,
            SourceScanFile.language,
            SourceScanFile.parse_status,
            SourceScanFile.parse_error,
            SourceScanFile.encoding,
        )
        .filter(SourceScanFile.source_id == source.id)
        .all()
    )
    spaces = _spaces(source)
    by_language: dict[str, Counter] = defaultdict(Counter)
    encodings: Counter = Counter()
    structured_rows = []
    copybooks: list[str] = []
    extensionless_text = 0
    size_skipped = 0
    non_utf8_skipped = 0
    for path, language, status, error, encoding in scan_rows:
        language = language or "unknown"
        by_language[language][status or "unreported"] += 1
        if language in STRUCTURED_LANGUAGES:
            structured_rows.append((path, status, error))
            if encoding:
                encodings[encoding] += 1
        if language == "copybook":
            copybooks.append(path)
        if language == "text" and not os.path.splitext(path)[1] and status != "skipped":
            extensionless_text += 1
        if status == "skipped":
            size_skipped += 1 if "überschreitet" in (error or "") else 0
            # Nur Quelltext-Sprachen: EBCDIC-Datendateien (.PS u. ä.) sind kein Befund.
            if language in STRUCTURED_LANGUAGES and "kein UTF-8" in (error or ""):
                non_utf8_skipped += 1

    profile = spaces.get("build_profile")
    gaps = parser_gaps(structured_rows)
    copies = copy_resolution(db, source.id, copybooks)
    structured_total = sum(
        sum(by_language[lang].values()) for lang in STRUCTURED_LANGUAGES if lang in by_language
    )

    hints: list[dict[str, str]] = []
    if structured_total and not profile:
        hints.append(
            {
                "code": "PROFILE_MISSING",
                "message": "Kein Buildprofil gesetzt: das Quellformat wird nur vermutet. "
                "Compilerfamilie, Quellformat und Codepage im Profil angeben.",
            }
        )
    fallback = sum(n for codec, n in encodings.items() if codec != "utf-8")
    if fallback:
        hints.append(
            {
                "code": "ENCODING_FALLBACK",
                "message": f"{fallback} Mainframe-Quelldatei(en) waren kein UTF-8 und wurden "
                "als cp1252 gelesen. Weicht die tatsächliche Codepage ab, 'encoding' im Profil setzen.",
            }
        )
    if non_utf8_skipped:
        hints.append(
            {
                "code": "NON_UTF8_SKIPPED",
                "message": f"{non_utf8_skipped} Datei(en) wurden als nicht lesbar übersprungen. "
                "Bei EBCDIC-Quellen die Codepage (z. B. CCSID-273) im Profil angeben.",
            }
        )
    if size_skipped:
        hints.append(
            {
                "code": "SIZE_LIMIT",
                "message": f"{size_skipped} Datei(en) überschreiten das Größenlimit und fehlen "
                "in der Strukturanalyse.",
            }
        )
    if extensionless_text and not spaces.get("language_paths"):
        hints.append(
            {
                "code": "EXTENSIONLESS_AS_TEXT",
                "message": f"{extensionless_text} Datei(en) ohne Endung gelten als Text. Liegen "
                "COBOL-Members darunter, 'language_paths' (Verzeichnis → cobol/copybook/jcl) setzen.",
            }
        )
    if copies["ambiguous"]:
        hints.append(
            {
                "code": "COPYBOOK_AMBIGUOUS",
                "message": f"{len(copies['ambiguous'])} COPY-Name(n) haben mehrere Kandidaten und "
                "bleiben deshalb offen. Mit 'copy_search_order' eine Bibliotheksreihenfolge festlegen.",
            }
        )
    if gaps:
        hints.append(
            {
                "code": "PARSER_GAPS",
                "message": "Die Grammatik meldet Fehler. Die häufigsten Muster stehen unter "
                "'parser_gaps'; sie bestimmen, welche Anweisungen als Nächstes unterstützt werden.",
            }
        )

    return {
        "source_id": source.id,
        "profile": {
            "build_profile": profile,
            "language_paths": spaces.get("language_paths"),
            "language_extensions": spaces.get("language_extensions"),
        },
        "files": {
            "total": len(scan_rows),
            "by_language": {
                lang: dict(sorted(statuses.items()))
                for lang, statuses in sorted(by_language.items())
            },
            "encodings": dict(sorted(encodings.items())),
        },
        "parser_gaps": gaps,
        "copybooks": copies,
        "hints": hints,
    }
