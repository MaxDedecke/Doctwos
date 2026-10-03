"""Konservative Struktur für SQL-Skripte: DDL-Objekte und DML-Anweisungen je Statement."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseResult
from resources._scan import Lines, mask

MAX_DML_ENTITIES = 500
_DDL = re.compile(
    r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?(?:UNIQUE\s+)?(?:MATERIALIZED\s+)?"
    r"(TABLE|VIEW|INDEX|SEQUENCE|TRIGGER|FUNCTION|PROCEDURE|TYPE|SCHEMA|TABLESPACE|USER|ROLE|DATABASE|DOMAIN|EXTENSION)\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"`\[\]]+)",
    re.IGNORECASE,
)
_DML = (
    ("INSERT", re.compile(r"^\s*INSERT\s+(?:INTO\s+)?([\w.\"`\[\]]+)", re.IGNORECASE)),
    ("UPDATE", re.compile(r"^\s*UPDATE\s+([\w.\"`\[\]]+)", re.IGNORECASE)),
    ("DELETE", re.compile(r"^\s*DELETE\s+FROM\s+([\w.\"`\[\]]+)", re.IGNORECASE)),
    ("ALTER", re.compile(r"^\s*ALTER\s+TABLE\s+(?:ONLY\s+)?([\w.\"`\[\]]+)", re.IGNORECASE)),
    ("SELECT", re.compile(r"^\s*SELECT\b.*?\bFROM\s+([\w.\"`\[\]]+)", re.IGNORECASE | re.DOTALL)),
)


def _statements(masked: str):
    """(start_offset, end_offset) je Statement; `$$`-Körper und Klammern bleiben zusammen."""
    start, depth, dollar = 0, 0, False
    for index, char in enumerate(masked):
        if masked.startswith("$$", index):
            dollar = not dollar
        elif not dollar:
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == ";" and depth == 0:
                yield start, index + 1
                start = index + 1
    if masked[start:].strip():
        yield start, len(masked)


def parse_sql_file(source: str, path: str, **_: object) -> ParseResult:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    masked = mask(source, line_comments=("--",), quotes="'")
    lines = Lines(source)
    root = Entity(
        type="sql_script", name=PurePosixPath(normalized).name, start_line=1,
        end_line=max(1, len(source.splitlines())), qualified_name=normalized,
        meta={"language": "sql", "is_file_root": True},
    )
    entities = [root]
    seen: dict[str, int] = {}
    dml = skipped = 0
    for start, end in _statements(masked):
        text = masked[start:end]
        first = len(text) - len(text.lstrip())
        begin_line, end_line = lines.line(start + first), lines.line(max(start, end - 1))
        ddl = _DDL.match(text)
        if ddl:
            kind, name = ddl.group(1).upper(), ddl.group(2).strip('"`[]')
            qname = f"{normalized}::{kind.lower()}:{name}"
            entity_type, meta = "sql_object", {"language": "sql", "object_type": kind.lower()}
            label = name
        else:
            hit = next(((kind, rx.match(text)) for kind, rx in _DML if rx.match(text)), None)
            if hit is None:
                continue
            dml += 1
            if dml > MAX_DML_ENTITIES:
                skipped += 1
                continue
            kind, match = hit
            table = match.group(1).strip('"`[]')
            qname = f"{normalized}::{kind.lower()}:{table}@{begin_line}"
            entity_type, label = "sql_statement", f"{kind} {table}"
            meta = {"language": "sql", "statement_type": kind.lower(), "table": table}
        seen[qname] = seen.get(qname, 0) + 1
        entities.append(Entity(
            type=entity_type, name=label, start_line=begin_line, end_line=end_line,
            parent_name=root.name, parent_qualified_name=normalized,
            qualified_name=qname if seen[qname] == 1 else f"{qname}#{seen[qname]}", meta=meta,
        ))
    if skipped:
        root.meta["dml_statements_not_modelled"] = skipped
    chunks = [
        Chunk(content=item["content"], start_line=item["start_line"], end_line=item["end_line"],
              meta={"language": "sql", "symbol_type": "source"})
        for item in CodeParser("sql").chunk_file(source)
    ]
    return ParseResult(program_name=PurePosixPath(normalized).stem, path=path, source_format="free",
                       entities=entities, edges=[], chunks=chunks)
