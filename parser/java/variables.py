"""Which local variable or parameter does a simple name denote at one source position?

Shared by the receiver resolution (``resolution.py``) and the data-flow tables of the relationship visitor
(``relationships.py``) so both answer the same way: a declaration is visible when it is declared before the use and the
use lies inside its lexical scope; of several visible declarations the one with the narrowest scope wins, then the
latest declaration.
"""

from __future__ import annotations

from typing import Literal

Status = Literal["found", "none", "ambiguous"]


def _coordinates(item) -> tuple[int, int]:
    meta = item.meta or {}
    return (
        int(meta.get("declaration_line", item.start_line or 0)),
        int(meta.get("declaration_column", 0)),
    )


def select_visible_variable(variables: list, use_line: int, use_column: int) -> tuple[list, Status]:
    """Return ``(selected, status)`` for the declarations of one name; ``status`` is found, none or ambiguous."""
    use_position = (use_line, use_column)
    visible = []
    for item in variables:
        meta = item.meta or {}
        declaration = _coordinates(item)
        scope_start = (int(meta.get("scope_start_line", item.start_line or 1)), int(meta.get("scope_start_column", 0)))
        scope_end = (int(meta.get("scope_end_line", item.end_line or 1_000_000)), int(meta.get("scope_end_column", 1_000_000)))
        if declaration <= use_position and scope_start <= use_position <= scope_end:
            extent = (scope_end[0] - scope_start[0], scope_end[1] - scope_start[1])
            visible.append((extent, declaration, item))
    if not visible:
        return [], "none"
    narrowest = min(item[0] for item in visible)
    in_nearest_scope = [item for item in visible if item[0] == narrowest]
    latest = max(item[1] for item in in_nearest_scope)
    selected = [item[2] for item in in_nearest_scope if item[1] == latest]
    return selected, ("found" if len(selected) == 1 else "ambiguous")
