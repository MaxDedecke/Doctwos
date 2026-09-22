"""COBOL file-I/O relationships (O-307).

This pass only emits relationships for explicit COBOL verbs and operands. It
does not infer a file from a record name or from a paragraph-wide word match.
Unknown or ambiguous operands remain unresolved.
"""

from __future__ import annotations

from .lexer import Token
from .model import CobolProgram, DataItem, FileDescriptor, ParsedEdge
from .names import canonical_identifier

_FILE_OPERATIONS = {
    "READ": "READS",
    "RETURN": "READS",
    "START": "READS",
    "WRITE": "WRITES",
    "REWRITE": "WRITES",
    "DELETE": "WRITES",
    "OPEN": "USES",
    "CLOSE": "USES",
}


def scan(
    program: CobolProgram,
    tokens: list[Token],
    file_descriptors: list[FileDescriptor],
    items: list[DataItem],
) -> list[ParsedEdge]:
    procedure = next(
        (division for division in program.divisions if division.name == "PROCEDURE"), None
    )
    if procedure is None or not file_descriptors:
        return []
    proc_tokens = [
        token for token in tokens if procedure.start_line <= token.phys_line <= procedure.end_line
    ]
    fd_names = {canonical_identifier(fd.name): fd.name for fd in file_descriptors}
    item_names = _item_names(program, file_descriptors, items)
    edges: list[ParsedEdge] = []

    for index, token in enumerate(proc_tokens):
        if token.kind != "WORD":
            continue
        operation = canonical_identifier(token.value)
        access = _FILE_OPERATIONS.get(operation)
        if access is None:
            continue
        if operation == "OPEN":
            _append_open_edges(
                edges,
                program,
                proc_tokens,
                index,
                fd_names,
                src=_enclosing_paragraph(program, token.phys_line),
            )
            continue
        operand = _next_word(proc_tokens, index + 1)
        if operand is None:
            continue
        fd_key = canonical_identifier(operand.value)
        fd_name = fd_names.get(fd_key)
        # READ addresses an FD, whereas the standard WRITE/REWRITE form
        # addresses the record description nested below that FD.  Both are
        # explicit I/O targets, but treating the latter as an unknown file
        # loses the connection from a paragraph to its data structure.
        item_qname = item_names.get(fd_key) if fd_name is None else None
        target_name = fd_name or (operand.value if item_qname is not None else operand.value)
        target_qname = f"{program.name}.{fd_name}" if fd_name is not None else item_qname
        target_kind = "file_fd" if fd_name is not None else "record" if item_qname else "unknown"
        target_resolution = "resolved" if target_qname is not None else "unresolved"
        src = _enclosing_paragraph(program, token.phys_line)
        fd_edge_meta = {
            "program": program.name,
            "operation": operation,
            "access": access,
            "io_target_kind": target_kind,
        }
        if target_qname is not None:
            fd_edge_meta["target_qualified_name"] = target_qname
        edges.append(
            ParsedEdge(
                type=access,
                src_name=src,
                dst_name=target_name,
                resolution=target_resolution,
                src_start_line=token.phys_line,
                src_end_line=operand.phys_line,
                scope=program.name,
                meta=fd_edge_meta,
            )
        )

        record = _associated_record(proc_tokens, index, operation)
        if record is None:
            continue
        record_key = canonical_identifier(record.value)
        target_qname = item_names.get(record_key)
        record_access = "WRITES" if access == "READS" else "READS"
        edges.append(
            ParsedEdge(
                type=record_access,
                src_name=src,
                dst_name=record.value,
                resolution="resolved" if target_qname is not None else "unresolved",
                src_start_line=token.phys_line,
                src_end_line=record.phys_line,
                scope=program.name,
                meta={
                    "program": program.name,
                    "operation": operation,
                    "access": record_access,
                    **({"target_qualified_name": target_qname} if target_qname else {}),
                },
            )
        )
    return edges


def _next_word(tokens: list[Token], start: int) -> Token | None:
    for token in tokens[start:]:
        if token.kind == "WORD":
            return token
        if token.kind in {"PERIOD", "STRING"}:
            return None
    return None


def _associated_record(tokens: list[Token], index: int, operation: str) -> Token | None:
    marker = (
        "INTO"
        if operation in {"READ", "RETURN"}
        else "FROM"
        if operation in {"WRITE", "REWRITE"}
        else None
    )
    if marker is None:
        return None
    for offset, token in enumerate(tokens[index + 1 :], index + 1):
        if token.kind == "PERIOD":
            return None
        if token.kind == "WORD" and canonical_identifier(token.value) == marker:
            return _next_word(tokens, offset + 1)
    return None


def _item_names(
    program: CobolProgram, file_descriptors: list[FileDescriptor], items: list[DataItem]
) -> dict[str, str | None]:
    qnames: dict[str, str | None] = {}
    for descriptor in file_descriptors:
        qnames[canonical_identifier(descriptor.name)] = f"{program.name}.{descriptor.name}"
    for item in items:
        parent = qnames.get(canonical_identifier(item.parent or "")) or program.name
        key = canonical_identifier(item.name)
        qname = f"{parent}.{item.name}"
        if key in qnames and qnames[key] != qname:
            qnames[key] = None
        else:
            qnames[key] = qname
    return qnames


def _append_open_edges(
    edges: list[ParsedEdge],
    program: CobolProgram,
    tokens: list[Token],
    start: int,
    fd_names: dict[str, str],
    *,
    src: str,
) -> None:
    mode = ""
    expecting_file = False
    for token in tokens[start + 1 :]:
        if token.kind == "PERIOD":
            break
        if token.kind != "WORD":
            continue
        word = canonical_identifier(token.value)
        if word in {"INPUT", "OUTPUT", "I-O", "EXTEND"}:
            mode = word
            expecting_file = True
            continue
        if not expecting_file:
            continue
        fd_name = fd_names.get(word)
        expecting_file = False
        edges.append(
            ParsedEdge(
                type="USES",
                src_name=src,
                dst_name=fd_name or token.value,
                resolution="resolved" if fd_name is not None else "unresolved",
                src_start_line=tokens[start].phys_line,
                src_end_line=token.phys_line,
                scope=program.name,
                meta={
                    "program": program.name,
                    "operation": "OPEN",
                    "open_mode": mode,
                    **({"dynamic": True} if fd_name is None else {}),
                },
            )
        )


def _enclosing_paragraph(program: CobolProgram, line: int) -> str:
    for paragraph in program.paragraphs:
        if paragraph.start_line <= line <= paragraph.end_line:
            return paragraph.name
    return ""
