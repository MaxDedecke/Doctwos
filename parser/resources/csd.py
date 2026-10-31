"""CICS-Ressourcendefinitionen (`DEFINE FILE(...) DSNAME(...)`).

Dialogprogramme nennen nur den CICS-Dateinamen. Erst diese Definition sagt, welches Dataset dahintersteht,
und verbindet sie so mit den Batch-Jobs, die dasselbe Dataset über eine DD-Anweisung verwenden.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseResult

_DEFINE = re.compile(r"^\s*DEFINE\s+(\w+)\(([^)]+)\)", re.IGNORECASE | re.MULTILINE)
_GROUP = re.compile(r"\bGROUP\(([^)]+)\)", re.IGNORECASE)
_DATASET = re.compile(r"\bDSNAME\(([^)]+)\)", re.IGNORECASE)


def parse_csd_file(source: str, path: str, **_: object) -> ParseResult:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    entities = [
        Entity(
            type="csd_file",
            name=PurePosixPath(normalized).name or normalized,
            start_line=1,
            end_line=max(1, len(source.splitlines())),
            qualified_name=normalized,
            meta={"language": "csd", "is_file_root": True},
        )
    ]
    root = entities[0]
    definitions = list(_DEFINE.finditer(source))
    for index, match in enumerate(definitions):
        if match.group(1).upper() != "FILE":
            continue
        end = definitions[index + 1].start() if index + 1 < len(definitions) else len(source)
        body = source[match.start() : end]
        group = _GROUP.search(body)
        dataset = _DATASET.search(body)
        name = match.group(2).strip()
        start_line = source.count("\n", 0, match.start()) + 1
        entities.append(
            Entity(
                type="cics_file",
                name=name,
                start_line=start_line,
                end_line=start_line + body.rstrip().count("\n"),
                parent_name=root.name,
                parent_qualified_name=normalized,
                qualified_name=f"{normalized}::{name}",
                meta={
                    "language": "csd",
                    "group": group.group(1).strip() if group else None,
                    "dataset": dataset.group(1).strip() if dataset else None,
                },
            )
        )
    chunks = [
        Chunk(
            content=item["content"],
            start_line=item["start_line"],
            end_line=item["end_line"],
            meta={"language": "csd", "symbol_type": "source"},
        )
        for item in CodeParser("csd").chunk_file(source)
    ]
    return ParseResult(
        program_name=PurePosixPath(normalized).stem or "csd",
        path=path,
        source_format="free",
        entities=entities,
        edges=[],
        chunks=chunks,
    )
