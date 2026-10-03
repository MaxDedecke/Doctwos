"""Konservative Struktur für Groovy-Dateien (Plugins, Build-Skripte).

Erfasst Klassen, Interfaces, Enums, Traits und Methoden mit exakten Zeilen.
Keine Typauflösung, keine Kanten: nur belegte Deklarationen.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseResult
from resources._scan import Lines, mask, matching_brace

_TYPE = re.compile(
    r"^[ \t]*(?:@\w+(?:\([^)]*\))?[ \t]*)*(?:(?:public|private|protected|abstract|final|static)[ \t]+)*"
    r"(class|interface|enum|trait)[ \t]+(\w+)[^{;]*\{",
    re.MULTILINE,
)
_METHOD = re.compile(
    r"^[ \t]*(?:@\w+(?:\([^)]*\))?[ \t]*)*(?:(?:public|private|protected|static|final|synchronized|abstract)[ \t]+)*"
    r"(?:def|void|[A-Za-z_][\w.<>\[\],?]*)[ \t]+(\w+)[ \t]*\(([^;{}]*)\)[ \t]*(?:throws[\w\s,.]+)?\{",
    re.MULTILINE,
)
_NOT_A_METHOD = {"if", "for", "while", "switch", "catch", "synchronized", "return", "new", "else", "try", "when"}
_NOT_A_TYPE = {"else", "return", "new", "throw", "assert", "case", "in"}


def parse_groovy_file(source: str, path: str, **_: object) -> ParseResult:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    masked = mask(source, line_comments=("//",), quotes="'\"", triple=True)
    lines = Lines(source)
    total = max(1, len(source.splitlines()))
    root = Entity(
        type="groovy_file", name=PurePosixPath(normalized).name, start_line=1, end_line=total,
        qualified_name=normalized, meta={"language": "groovy", "is_file_root": True},
    )
    package = re.search(r"^[ \t]*package[ \t]+([\w.]+)", masked, re.MULTILINE)
    if package:
        root.meta["package"] = package.group(1)

    entities = [root]
    spans: list[tuple[int, int, Entity]] = []  # type entities for parent lookup
    seen: dict[str, int] = {}

    def unique(qname: str) -> str:
        seen[qname] = seen.get(qname, 0) + 1
        return qname if seen[qname] == 1 else f"{qname}#{seen[qname]}"

    for match in _TYPE.finditer(masked):
        brace = match.end() - 1
        end = matching_brace(masked, brace)
        if end is None:
            continue
        name = match.group(2)
        entity = Entity(
            type="class" if match.group(1) != "interface" else "interface",
            name=name, start_line=lines.line(match.start(2)), end_line=lines.line(end),
            parent_name=root.name, parent_qualified_name=normalized,
            qualified_name=unique(f"{normalized}::{name}"),
            meta={"language": "groovy", "kind": match.group(1)},
        )
        entities.append(entity)
        spans.append((brace, end, entity))

    for match in _METHOD.finditer(masked):
        name = match.group(1)
        head = masked[match.start():match.start(1)].split()
        if name in _NOT_A_METHOD or (head and head[-1] in _NOT_A_TYPE):
            continue
        brace = match.end() - 1
        end = matching_brace(masked, brace)
        if end is None:
            continue
        owners = [span for span in spans if span[0] < match.start() < span[1]]
        owner = min(owners, key=lambda span: span[1] - span[0])[2] if owners else root
        entities.append(Entity(
            type="method", name=name, start_line=lines.line(match.start(1)), end_line=lines.line(end),
            parent_name=owner.name, parent_qualified_name=owner.qualified_name,
            qualified_name=unique(f"{owner.qualified_name}#{name}"),
            meta={"language": "groovy", "parameters": " ".join(match.group(2).split())[:200]},
        ))
    chunks = [
        Chunk(content=item["content"], start_line=item["start_line"], end_line=item["end_line"],
              meta={"language": "groovy", "symbol_type": "source"})
        for item in CodeParser("groovy").chunk_file(source)
    ]
    return ParseResult(program_name=PurePosixPath(normalized).stem, path=path, source_format="free",
                       entities=entities, edges=[], chunks=chunks)
