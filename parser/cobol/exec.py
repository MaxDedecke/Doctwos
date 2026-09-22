"""Conservative extraction for embedded EXEC dialects other than SQL.

The COBOL lexer deliberately never sees embedded syntax.  This module works
on :class:`EmbeddedBlock` instead and records facts that are explicit in the
source: the dialect, its first operation word, and named CICS/IMS resources.
Unknown dialects are retained as blocks with an ``OTHER`` operation instead
of being silently dropped.  This is intentionally not a CICS or IMS parser.
"""

from __future__ import annotations

import re

from .embedded import EmbeddedBlock
from .model import CobolProgram, ExecBlock, ExecResource, ParsedEdge

_LEADING_EXEC_RE = re.compile(r"\A\s*EXEC\s+\S+\s*", re.IGNORECASE)
_END_EXEC_RE = re.compile(r"END-EXEC", re.IGNORECASE)
_OPERATION_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
_RESOURCE_RE = re.compile(
    r"\b(PROGRAM|FILE|DATASET|QUEUE|TRANSID|MAP|MAPSET|TERMID|"
    r"PCB|PSB|PSBNAME|SEGMENT|DATABASE|DBDNAME|TDQUEUE|TSQUEUE|"
    r"CHANNEL|CONTAINER|URIMAP|WEBSERVICE|PIPELINE|TCPIPSERVICE|"
    r"MQNAME|TOPIC|APPLID|CONNECTION|SESSION|TRANSACTION)\s*\(\s*"
    r"(?:'([^']*)'|\"([^\"]*)\"|([A-Za-z][A-Za-z0-9-]*))\s*\)",
    re.IGNORECASE,
)


def scan(
    program: CobolProgram,
    blocks: list[EmbeddedBlock],
    own_range: tuple[int, int] | None = None,
) -> tuple[list[ExecBlock], list[ParsedEdge], list[str]]:
    exec_blocks: list[ExecBlock] = []
    edges: list[ParsedEdge] = []

    for block in blocks:
        dialect = _normalize_dialect(block.dialect)
        if dialect == "SQL":
            continue
        if own_range is not None and not own_range[0] <= block.start_line <= own_range[1]:
            continue

        body = _strip_wrapper(block.content)
        operation = _operation(body)
        resources = _resources(body)
        name = f"EXEC-{dialect}-BLOCK@{block.start_line}"
        exec_block = ExecBlock(
            name=name,
            dialect=dialect,
            operation=operation,
            start_line=block.start_line,
            end_line=block.end_line,
            resources=resources,
        )
        exec_blocks.append(exec_block)

        block_qname = f"{program.name}.{name}"
        operation_qname = f"{block_qname}.{operation}@{block.start_line}"
        common = {
            "program": program.name,
            "dialect": dialect,
            "language": "cobol",
        }
        edges.append(
            ParsedEdge(
                type="EXECUTES",
                src_name=block_qname,
                dst_name=operation,
                resolution="resolved",
                src_start_line=block.start_line,
                src_end_line=block.end_line,
                scope=program.name,
                meta={**common, "target_qualified_name": operation_qname},
            )
        )
        for resource in resources:
            resource_qname = (
                f"{program.name}.EXEC-RESOURCE@{dialect}:{resource.kind}:{resource.name}"
            )
            edges.append(
                ParsedEdge(
                    type="USES",
                    src_name=block_qname,
                    dst_name=resource.name,
                    resolution="dynamic" if resource.dynamic else "resolved",
                    src_start_line=block.start_line,
                    src_end_line=block.end_line,
                    scope=program.name,
                    meta={
                        **common,
                        "resource_kind": resource.kind,
                        "target_qualified_name": resource_qname,
                    },
                )
            )

        # CICS LINK and XCTL name an actual COBOL program when PROGRAM has a
        # literal operand. Preserve that control-flow fact in addition to the
        # resource edge so callers can navigate after global CALL resolution.
        # A variable operand is evidence too, but must remain dynamic.
        if dialect == "CICS" and operation in {"LINK", "XCTL"}:
            for resource in resources:
                if resource.kind != "PROGRAM":
                    continue
                edges.append(
                    ParsedEdge(
                        type="CALL",
                        src_name=block_qname,
                        dst_name=resource.name,
                        resolution="dynamic" if resource.dynamic else "resolved",
                        src_start_line=block.start_line,
                        src_end_line=block.end_line,
                        meta={
                            **common,
                            "invocation_kind": f"cics_{operation.lower()}",
                            "resource_kind": "PROGRAM",
                        },
                    )
                )

    return exec_blocks, edges, []


def _normalize_dialect(dialect: str) -> str:
    """Keep the common ``EXEC DL/I`` spelling on the DLI identity."""
    normalized = dialect.upper()
    return "DLI" if normalized in {"DL/I", "DLI"} else normalized


def _strip_wrapper(content: str) -> str:
    body = _LEADING_EXEC_RE.sub("", content, count=1)
    match = _END_EXEC_RE.search(body)
    return body[: match.start()] if match else body


def _operation(body: str) -> str:
    match = _OPERATION_RE.search(body)
    return match.group(0).upper() if match else "OTHER"


def _resources(body: str) -> list[ExecResource]:
    seen: set[tuple[str, str]] = set()
    result: list[ExecResource] = []
    for match in _RESOURCE_RE.finditer(body):
        kind = match.group(1).upper()
        literal = match.group(2) if match.group(2) is not None else match.group(3)
        variable = match.group(4)
        name = literal if literal is not None else variable
        if not name:
            continue
        key = (kind, name.upper())
        if key not in seen:
            seen.add(key)
            result.append(ExecResource(kind=kind, name=name, dynamic=variable is not None))
    return result
