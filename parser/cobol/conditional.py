"""Sichere, kleine Auswertung von COBOL-Compilerbedingungen (O-124)."""

from __future__ import annotations

import re

from .model import LogicalLine

_IF = re.compile(r"^>>\s*IF\s+(.+?)\s*$", re.I)
_ELSE = re.compile(r"^>>\s*ELSE\s*$", re.I)
_END = re.compile(r"^>>\s*END-IF\s*$", re.I)
_EQ = re.compile(r"^(\d+)\s*=\s*(\d+)$")
_DEFINED = re.compile(r"^DEFINED\s*\(\s*([A-Z][A-Z0-9-]*)\s*\)$", re.I)


def apply(lines: list[LogicalLine], defines: dict[str, str]) -> list[LogicalLine]:
    """Filtert nur sicher inaktive Zweige; unbekannte bleiben belegt erhalten."""
    result: list[LogicalLine] = []
    stack: list[tuple[bool | None, bool, str]] = []
    for line in lines:
        directive = line.directive or ""
        if match := _IF.match(directive):
            value = _evaluate(match.group(1), defines)
            stack.append((value, False, match.group(1)))
            result.append(line)
            continue
        if _ELSE.match(directive) and stack:
            value, _, expr = stack[-1]
            stack[-1] = (value, True, expr)
            result.append(line)
            continue
        if _END.match(directive) and stack:
            stack.pop()
            result.append(line)
            continue
        state, condition = _state(stack)
        if state is False:
            line.is_comment = True
        elif condition:
            line.condition = condition
        result.append(line)
    return result


def _state(stack: list[tuple[bool | None, bool, str]]) -> tuple[bool | None, str | None]:
    unknown: list[str] = []
    for value, is_else, expr in stack:
        active = None if value is None else (not value if is_else else value)
        if active is False:
            return False, None
        if active is None:
            unknown.append(f"NOT ({expr})" if is_else else expr)
    return (None, " AND ".join(unknown)) if unknown else (True, None)


def _evaluate(expr: str, defines: dict[str, str]) -> bool | None:
    if match := _EQ.match(expr.strip()):
        return match.group(1) == match.group(2)
    if match := _DEFINED.match(expr.strip()):
        name = match.group(1).upper()
        return name in {key.upper() for key in defines}
    return None
