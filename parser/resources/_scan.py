"""Gemeinsame Hilfen für die schlanken Skript-Parser (Groovy, JavaScript, SQL).

Kein Ausführen, kein Auflösen: Kommentare und Zeichenketten werden durch
Leerzeichen gleicher Länge ersetzt (Zeilenumbrüche bleiben), damit Muster und
Klammerzählung nie in Text greifen und Zeilennummern wahr bleiben.
"""
from __future__ import annotations

import bisect
import re


def mask(source: str, *, line_comments: tuple[str, ...], block: bool = True,
         quotes: str = "'\"", triple: bool = False) -> str:
    out: list[str] = []
    i, n = 0, len(source)

    def blank(text: str) -> str:
        return re.sub(r"[^\n]", " ", text)

    while i < n:
        ch = source[i]
        if block and source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append(blank(source[i:end]))
            i = end
            continue
        marker = next((m for m in line_comments if source.startswith(m, i)), None)
        if marker:
            end = source.find("\n", i)
            end = n if end < 0 else end
            out.append(blank(source[i:end]))
            i = end
            continue
        if ch in quotes:
            delimiter = ch * 3 if triple and source.startswith(ch * 3, i) else ch
            j = i + len(delimiter)
            while j < n:
                if source[j] == "\\" and len(delimiter) == 1:
                    j += 2
                    continue
                if source.startswith(delimiter, j):
                    j += len(delimiter)
                    break
                if delimiter == ch and ch != "`" and source[j] == "\n":
                    break  # unterminated single-line string: stop at the line end
                j += 1
            out.append(blank(source[i:j]))
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


class Lines:
    """Offset -> 1-basierte Zeilennummer."""

    def __init__(self, text: str) -> None:
        self._starts = [0] + [m.end() for m in re.finditer(r"\n", text)]

    def line(self, offset: int) -> int:
        return bisect.bisect_right(self._starts, offset)


def matching_brace(masked: str, open_index: int) -> int | None:
    """Offset der passenden `}` zu `masked[open_index] == '{'`, sonst None."""
    depth = 0
    for index in range(open_index, len(masked)):
        char = masked[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None
