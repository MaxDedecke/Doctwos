"""Struktur für Java-`.properties`-Dateien (Message-Bundles, Konfiguration).

Bewusst klein: ein Dateiwurzel-Entity je Datei und je Basis-Bundle ein
`property`-Entity pro Schlüssel mit Quellzeilen. Übersetzungsdateien
(`messages_de.properties`) bekommen nur die Wurzel mit Bundle/Locale, damit ein
Bundle mit vielen Sprachen den Entity-Bestand nicht vervielfacht.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseResult

_LOCALE_SUFFIX = re.compile(r"^(?P<bundle>.+?)_(?P<locale>[a-z]{2,3}(?:_[A-Za-z]{2,4})?)$")
_SECRET_KEY = re.compile(r"pass(word|wd)?|secret|token|credential|private|api[._-]?key", re.IGNORECASE)
_VALUE_PREVIEW = 120


def split_bundle_locale(path: str) -> tuple[str, str | None]:
    """`dir/messages_de_CH.properties` -> (`dir/messages`, `de_CH`)."""
    posix = PurePosixPath(path.replace("\\", "/"))
    match = _LOCALE_SUFFIX.match(posix.stem)
    stem = match.group("bundle") if match else posix.stem
    return (posix.parent / stem).as_posix().lstrip("./"), match.group("locale") if match else None


def _logical_entries(source: str):
    """Yield (start_line, end_line, raw_logical_line) ohne Kommentare/Leerzeilen."""
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        start = index + 1
        text = lines[index]
        index += 1
        stripped = text.lstrip()
        if not stripped or stripped[0] in "#!":
            continue
        while _continues(text) and index < len(lines):
            text = text[:-1] + lines[index].lstrip()
            index += 1
        yield start, index, text


def _continues(text: str) -> bool:
    trailing = len(text) - len(text.rstrip("\\"))
    return trailing % 2 == 1


def _split_key_value(logical: str) -> tuple[str, str]:
    text = logical.lstrip()
    key: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            key.append(text[i + 1])
            i += 2
            continue
        if ch in "=: \t\f":
            break
        key.append(ch)
        i += 1
    rest = text[i:].lstrip(" \t\f")
    if rest[:1] in ("=", ":"):
        rest = rest[1:].lstrip(" \t\f")
    return "".join(key), rest


def parse_properties_file(source: str, path: str, **_: object) -> ParseResult:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    bundle, locale = split_bundle_locale(normalized)
    entries = list(_logical_entries(source))
    total_lines = max(1, len(source.splitlines()))
    root = Entity(
        type="properties_file", name=PurePosixPath(normalized).name or normalized,
        start_line=1, end_line=total_lines, qualified_name=normalized,
        meta={
            "language": "properties", "is_file_root": True, "bundle": bundle,
            "locale": locale, "property_count": len(entries),
        },
    )
    entities = [root]
    if locale is None:
        seen: dict[str, int] = {}
        for start, end, logical in entries:
            key, value = _split_key_value(logical)
            if not key:
                continue
            occurrence = seen.get(key, 0) + 1
            seen[key] = occurrence
            suffix = "" if occurrence == 1 else f"#{occurrence}"
            meta = {"language": "properties", "bundle": bundle, "property_key": key}
            if _SECRET_KEY.search(key):
                meta["value_redacted"] = True
            else:
                meta["value_preview"] = value[:_VALUE_PREVIEW]
            entities.append(Entity(
                type="property", name=key, start_line=start, end_line=end,
                parent_name=root.name, parent_qualified_name=normalized,
                qualified_name=f"{normalized}::{key}{suffix}", meta=meta,
            ))
    chunks = [
        Chunk(content=item["content"], start_line=item["start_line"], end_line=item["end_line"],
              meta={"language": "properties", "symbol_type": "source", "bundle": bundle})
        for item in CodeParser("properties").chunk_file(source)
    ]
    return ParseResult(
        program_name=PurePosixPath(normalized).stem or "properties", path=path,
        source_format="free", entities=entities, edges=[], chunks=chunks,
    )
