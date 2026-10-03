"""Konservative Struktur für JavaScript-Dateien: Funktionen, Klassen, Methoden."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseResult
from resources._scan import Lines, mask, matching_brace

_CLASS = re.compile(r"^[ \t]*(?:export[ \t]+(?:default[ \t]+)?)?class[ \t]+(\w+)[^{;]*\{", re.MULTILINE)
_FUNCTION = re.compile(
    r"^[ \t]*(?:export[ \t]+(?:default[ \t]+)?)?(?:async[ \t]+)?function\*?[ \t]*(\w+)[ \t]*\([^)]*\)[ \t]*\{",
    re.MULTILINE,
)
_ASSIGNED = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+(\w+)[ \t]*=[ \t]*(?:async[ \t]+)?"
    r"(?:function\*?[ \t]*\w*[ \t]*\([^)]*\)|\([^)]*\)[ \t]*=>|\w+[ \t]*=>)[ \t]*\{",
    re.MULTILINE,
)
_METHOD = re.compile(
    r"^[ \t]+(?:static[ \t]+)?(?:async[ \t]+)?(?:get[ \t]+|set[ \t]+)?(\w+)[ \t]*\([^)]*\)[ \t]*\{",
    re.MULTILINE,
)
_KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "with", "else"}


def parse_javascript_file(source: str, path: str, **_: object) -> ParseResult:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    masked = mask(source, line_comments=("//",), quotes="'\"`")
    lines = Lines(source)
    root = Entity(
        type="javascript_file", name=PurePosixPath(normalized).name, start_line=1,
        end_line=max(1, len(source.splitlines())), qualified_name=normalized,
        meta={"language": "javascript", "is_file_root": True},
    )
    entities = [root]
    seen: dict[str, int] = {}

    def unique(qname: str) -> str:
        seen[qname] = seen.get(qname, 0) + 1
        return qname if seen[qname] == 1 else f"{qname}#{seen[qname]}"

    classes: list[tuple[int, int, Entity]] = []
    for match in _CLASS.finditer(masked):
        end = matching_brace(masked, match.end() - 1)
        if end is None:
            continue
        entity = Entity(
            type="class", name=match.group(1), start_line=lines.line(match.start(1)),
            end_line=lines.line(end), parent_name=root.name, parent_qualified_name=normalized,
            qualified_name=unique(f"{normalized}::{match.group(1)}"), meta={"language": "javascript"},
        )
        entities.append(entity)
        classes.append((match.end() - 1, end, entity))

    def add_function(match: re.Match[str]) -> None:
        end = matching_brace(masked, match.end() - 1)
        if end is None:
            return
        entities.append(Entity(
            type="function", name=match.group(1), start_line=lines.line(match.start(1)),
            end_line=lines.line(end), parent_name=root.name, parent_qualified_name=normalized,
            qualified_name=unique(f"{normalized}::{match.group(1)}"), meta={"language": "javascript"},
        ))

    taken = set()
    for pattern in (_FUNCTION, _ASSIGNED):
        for match in pattern.finditer(masked):
            if any(start < match.start() < stop for start, stop, _ in classes):
                continue
            taken.add(match.start(1))
            add_function(match)
    for match in _METHOD.finditer(masked):
        name = match.group(1)
        owners = [c for c in classes if c[0] < match.start() < c[1]]
        if name in _KEYWORDS or not owners or match.start(1) in taken:
            continue
        owner = min(owners, key=lambda c: c[1] - c[0])[2]
        end = matching_brace(masked, match.end() - 1)
        if end is None:
            continue
        entities.append(Entity(
            type="method", name=name, start_line=lines.line(match.start(1)), end_line=lines.line(end),
            parent_name=owner.name, parent_qualified_name=owner.qualified_name,
            qualified_name=unique(f"{owner.qualified_name}#{name}"), meta={"language": "javascript"},
        ))
    chunks = [
        Chunk(content=item["content"], start_line=item["start_line"], end_line=item["end_line"],
              meta={"language": "javascript", "symbol_type": "source"})
        for item in CodeParser("javascript").chunk_file(source)
    ]
    return ParseResult(program_name=PurePosixPath(normalized).stem, path=path, source_format="free",
                       entities=entities, edges=[], chunks=chunks)
