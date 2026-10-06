"""Struktur für AsciiDoc-Dokumente (Referenz-/Benutzerhandbücher im Repository).

Bewusst klein und deterministisch: ein Dateiwurzel-Entity (`asciidoc_document`), je Überschrift ein
`doc_section`-Entity mit Zeilenbereich und Verschachtelung, `INCLUDES`-Kanten für `include::`-Direktiven
und `DOCUMENTS`-Kanten für Namen, die ein Abschnitt in Inline-Code nennt (Typen, voll qualifizierte
Namen, Property-Schlüssel, Dateipfade). Aufgelöst werden diese Kanten quellenweit in
`core/doc_resolution.py`; eindeutig oder gar nicht, es wird nichts geraten. Blöcke mit wörtlichem
Inhalt (Listing, Literal, Passthrough, Kommentar) werden weder nach Überschriften noch nach Namen
durchsucht.
"""
from __future__ import annotations

import posixpath
import re
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseResult, ParsedEdge

_HEADING = re.compile(r"^(={1,6})\s+(\S.*?)\s*=*\s*$")
_ANCHOR = re.compile(r"^\[\[([^\],\s]+)(?:,[^\]]*)?\]\]\s*$|^\[#([^\],\s]+)[^\]]*\]\s*$")
_INCLUDE = re.compile(r"^include::([^\[\]]+)\[[^\]]*\]\s*$")
_INLINE_CODE = re.compile(r"``?([^`\n]+?)``?")
_FENCE = re.compile(r"^(-{4,}|\.{4,}|\+{4,}|/{4,})\s*$")

_TYPE_NAME = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
_QUALIFIED = re.compile(r"^[a-z][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_$]*)+$")
_PROPERTY_KEY = re.compile(r"^[a-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+)+$")
_PATH = re.compile(r"^[\w./-]+/[\w.-]+\.(?:xml|properties|java|adoc|groovy|js|json|yml|yaml|sql|html|xsl|xslt|sh|cfg|conf)$")
_MAX_MENTIONS_PER_FILE = 400
_MIN_TYPE_NAME = 4


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def _clean_title(text: str) -> str:
    """Überschrift ohne Inline-Auszeichnung (`*fett*`, `_kursiv_`, Backticks)."""
    return re.sub(r"[*_`+]", "", text).strip() or text.strip()


def classify_mention(text: str) -> tuple[str, str] | None:
    """Ein Inline-Code-Inhalt als (Art, Name), falls er wie ein Verweis auf ein Objekt aussieht."""
    value = text.strip().rstrip("()").lstrip("@").strip()
    if not value or len(value) > 160:
        return None
    if _PATH.match(value):
        return "file_path", value
    if _QUALIFIED.match(value) and value.rsplit(".", 1)[-1][:1].isupper():
        return "qualified_name", value
    if _TYPE_NAME.match(value) and len(value) >= _MIN_TYPE_NAME and any(c.islower() for c in value):
        return "type_name", value
    if _PROPERTY_KEY.match(value):
        return "property_key", value
    return None


def _relative(path: str, value: str) -> str | None:
    value = value.strip()
    if not value or "{" in value or "://" in value or value.startswith("/"):
        return None
    base = PurePosixPath(path.replace("\\", "/")).parent.as_posix()
    resolved = posixpath.normpath(posixpath.join(base, value))
    return None if resolved.startswith("..") else resolved.lstrip("./")


def parse_asciidoc_file(source: str, path: str, **_: object) -> ParseResult:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    lines = source.splitlines()
    last_line = max(1, len(lines))

    # --- Überschriften (außerhalb wörtlicher Blöcke) und Zeilen, die Namen/Includes enthalten dürfen ---
    headings: list[dict] = []
    scannable: list[tuple[int, str]] = []
    fence: str | None = None
    pending_anchor: str | None = None
    for number, text in enumerate(lines, start=1):
        marker = _FENCE.match(text)
        if marker:
            token = marker.group(1)[0]
            fence = None if fence == token else (token if fence is None else fence)
            continue
        if fence is not None:
            continue
        anchor = _ANCHOR.match(text)
        if anchor:
            pending_anchor = anchor.group(1) or anchor.group(2)
            continue
        heading = _HEADING.match(text)
        if heading:
            headings.append({"level": len(heading.group(1)) - 1, "title": _clean_title(heading.group(2)),
                             "line": number, "anchor": pending_anchor})
            pending_anchor = None
            scannable.append((number, text))
            continue
        if text.strip():
            pending_anchor = None
        scannable.append((number, text))

    title = next((h["title"] for h in headings if h["level"] == 0), None)
    root = Entity(type="asciidoc_document", name=PurePosixPath(normalized).name or normalized, start_line=1,
                  end_line=last_line, qualified_name=normalized,
                  meta={"language": "asciidoc", "is_file_root": True, "doc_title": title})
    entities = [root]

    # --- Abschnitte: Ende = Zeile vor der nächsten Überschrift gleicher oder höherer Ebene ---
    used: dict[str, int] = {}
    stack: list[tuple[int, str, str]] = []  # (level, name, qualified_name)
    sections: list[tuple[int, int, str]] = []  # (start, end, qname)
    for index, heading in enumerate(headings):
        end = last_line
        for later in headings[index + 1:]:
            if later["level"] <= heading["level"]:
                end = later["line"] - 1
                break
        slug = _slug(heading["anchor"] or heading["title"])
        used[slug] = used.get(slug, 0) + 1
        qname = f"{normalized}::section:{slug}" + ("" if used[slug] == 1 else f"#{used[slug]}")
        while stack and stack[-1][0] >= heading["level"]:
            stack.pop()
        parent_name, parent_qname = (stack[-1][1], stack[-1][2]) if stack else (root.name, normalized)
        entities.append(Entity(type="doc_section", name=heading["title"], start_line=heading["line"],
                               end_line=max(heading["line"], end), parent_name=parent_name,
                               parent_qualified_name=parent_qname, qualified_name=qname,
                               meta={"language": "asciidoc", "level": heading["level"], "anchor": heading["anchor"]}))
        stack.append((heading["level"], heading["title"], qname))
        sections.append((heading["line"], max(heading["line"], end), qname))

    def section_for(line: int) -> str:
        enclosing = [item for item in sections if item[0] <= line <= item[1]]
        return min(enclosing, key=lambda item: item[1] - item[0])[2] if enclosing else normalized

    # --- Kanten ---
    edges: list[ParsedEdge] = []
    seen: set[tuple[str, str]] = set()
    mentions = 0
    for number, text in scannable:
        include = _INCLUDE.match(text)
        if include:
            target = _relative(normalized, include.group(1))
            edges.append(ParsedEdge(type="INCLUDES", src_name=section_for(number), dst_name=target or include.group(1).strip(),
                resolution="unresolved" if target else "dynamic", src_start_line=number, src_end_line=number,
                meta={"language": "asciidoc", "target_file_path": target, "target_entity_type": "asciidoc_document",
                      "source_file_path": normalized}))
            continue
        if _HEADING.match(text) or text.lstrip().startswith(":"):
            continue
        for match in _INLINE_CODE.finditer(text):
            if mentions >= _MAX_MENTIONS_PER_FILE:
                break
            classified = classify_mention(match.group(1))
            if classified is None:
                continue
            kind, name = classified
            source_name = section_for(number)
            if (source_name, name) in seen:
                continue
            seen.add((source_name, name))
            mentions += 1
            edges.append(ParsedEdge(type="DOCUMENTS", src_name=source_name, dst_name=name, resolution="unresolved",
                src_start_line=number, src_end_line=number,
                meta={"language": "asciidoc", "mention_kind": kind, "source_file_path": normalized}))

    chunks = [Chunk(content=item["content"], start_line=item["start_line"], end_line=item["end_line"],
                    meta={"language": "asciidoc", "symbol_type": "documentation"})
              for item in CodeParser("asciidoc").chunk_file(
                  source, boundary_lines=frozenset(h["line"] for h in headings if h["line"] > 1))]
    return ParseResult(program_name=PurePosixPath(path).stem or "document", path=path, source_format="free",
                       entities=entities, edges=edges, chunks=chunks)
