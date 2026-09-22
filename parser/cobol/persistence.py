"""COBOL-specific edge identity and local-scope rules.
The database persistence contract itself lives in :mod:`structure_persist`.
This module contains only the rules that depend on COBOL entity names and
program boundaries, so adding another language cannot accidentally inherit
COBOL's paragraph/data-item assumptions.
"""

from __future__ import annotations

from core.model import ParsedEdge
from models.database import CodeEntity


LOCAL_TARGET_TYPES: dict[str, tuple[str, ...]] = {
    "PERFORM": ("paragraph", "section"),
    "GOTO": ("paragraph", "section"),
    "USES": ("data_item", "exec_resource"),
    "EXECUTES": ("exec_operation",),
    "INCLUDES": ("sql_include",),
    "DEFINES": ("data_item",),
}

SOURCE_TYPES: dict[str, tuple[str, ...]] = {
    "CALL": ("program", "paragraph"),
    "PERFORM": ("program", "paragraph"),
    "GOTO": ("program", "paragraph"),
    "COPY": ("program", "paragraph"),
    "USES": ("program", "paragraph", "sql_block", "exec_block"),
    "EXECUTES": ("exec_block",),
    "INCLUDES": ("sql_block",),
    "DEFINES": ("file_fd",),
}


def belongs_to_program(row: CodeEntity, program_name: str) -> bool:
    """Return whether a COBOL entity belongs to the named program."""
    if not row.qualified_name:
        return False
    return row.qualified_name.split(".", 1)[0].upper() == program_name.upper()


def parent_name(row: CodeEntity, by_qname: dict[str, CodeEntity]) -> str | None:
    if not row.qualified_name or "." not in row.qualified_name:
        return None
    parent = by_qname.get(row.qualified_name.rsplit(".", 1)[0])
    return parent.name if parent else None


def find_source(
    edge: ParsedEdge, by_qname: dict[str, CodeEntity], by_name: dict[str, list[CodeEntity]]
) -> CodeEntity | None:
    """Find a COBOL source entity while preserving program scoping rules."""
    if not edge.src_name:
        program_hint = (edge.meta or {}).get("program")
        if program_hint:
            hinted = [
                row for row in by_name.get(program_hint.upper(), []) if row.type == "program"
            ]
            if len(hinted) == 1:
                return hinted[0]
        return next((row for row in by_qname.values() if row.type == "program"), None)

    allowed = SOURCE_TYPES.get(edge.type)
    candidates = [
        row
        for row in by_name.get(edge.src_name.upper(), [])
        if allowed is None or row.type in allowed
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        # The source is an already parsed fact; retain the historic first-match
        # behavior here. Target resolution below never makes this compromise.
        return candidates[0]
    return None


def resolve_local_target(
    edge: ParsedEdge, by_qname: dict[str, CodeEntity], by_name: dict[str, list[CodeEntity]]
) -> CodeEntity | None:
    """Resolve PERFORM/GOTO/USES/DEFINES inside one COBOL program."""
    target_qname = (edge.meta or {}).get("target_qualified_name")
    if target_qname:
        direct = by_qname.get(target_qname)
        if direct is not None:
            return direct
    allowed = LOCAL_TARGET_TYPES.get(edge.type)
    candidates = [
        row
        for row in by_name.get(edge.dst_name.upper(), [])
        if allowed is None or row.type in allowed
    ]
    program_hint = (edge.meta or {}).get("program")
    if program_hint:
        scoped = [row for row in candidates if belongs_to_program(row, program_hint)]
        if len(scoped) != len(candidates):
            candidates = scoped

    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        parent_hint = (edge.meta or {}).get("parent")
        if parent_hint:
            narrowed = [
                row
                for row in candidates
                if (parent_name(row, by_qname) or "").upper() == parent_hint.upper()
            ]
            if len(narrowed) == 1:
                return narrowed[0]
    return None
