"""Übersetzungseinheiten einer Datei: Programme der obersten Ebene, je bis zu ihrem END PROGRAM.

Die Grammatik kann eine Datei mit vielen Programmen als einen Baum lesen, ihre Fehlerkorrektur aber nicht: Ab einer
unbekannten Anweisung (ein Dialekt) gehen sonst alle folgenden Programme der Datei verloren. Jede Einheit wird deshalb
für sich geparst. Verschachtelte Programme bleiben in der Einheit ihres äußeren Programms. Die Zeilennummern bleiben
erhalten, weil der Grammatiktext ohnehin mit Leerzeilen bis zur ersten physischen Zeile aufgefüllt wird.
"""

from __future__ import annotations

import re

from .model import LogicalLine

_PROGRAM_ID_RE = re.compile(r"(?i)^\s*PROGRAM-ID\b")
_END_PROGRAM_RE = re.compile(r"(?i)^\s*END\s+PROGRAM\b")


def split(lines: list[LogicalLine]) -> list[list[LogicalLine]]:
    """Zerlegt in Einheiten. Ohne erkennbare Grenze (der Normalfall: ein Programm) bleibt es bei einer Einheit."""
    units: list[list[LogicalLine]] = []
    current: list[LogicalLine] = []
    depth = 0
    for line in lines:
        current.append(line)
        if line.is_comment:
            continue
        if _PROGRAM_ID_RE.match(line.text):
            depth += 1
        elif _END_PROGRAM_RE.match(line.text) and depth > 0:
            depth -= 1
            if depth == 0:
                units.append(current)
                current = []
    if current:
        if units and not any(not line.is_comment and line.text.strip() for line in current):
            # Nur Leerzeilen/Kommentare nach dem letzten END PROGRAM: zur letzten Einheit.
            units[-1].extend(current)
        else:
            units.append(current)
    return units or [lines]


def containing(lines: list[LogicalLine], line_no: int) -> list[LogicalLine]:
    """Die Einheit, zu der eine physische Zeile gehört (sonst die ganze Datei)."""
    for unit in split(lines):
        if unit and unit[0].phys_start_line <= line_no <= unit[-1].phys_end_line:
            return unit
    return lines
