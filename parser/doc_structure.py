"""Struktur von hochgeladenen Dokumenten: Markdown-Überschriften als Chunk-Grenzen und
Abschnittspfade, damit Chunks (und damit Code-Doku-Links) einem Abschnitt und einem
Zeilenbereich des Originals zugeordnet werden können."""

from __future__ import annotations

import re

_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^ {0,3}(```|~~~)")

Outline = list[tuple[int, int, str]]  # (1-basierte Zeile, Ebene, Titel)


def markdown_outline(text: str) -> Outline:
    """Überschriften eines Markdown-Textes; Zeilen in Codeblöcken (```/~~~) zählen nicht."""
    outline: Outline = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match and match.group(2):
            outline.append((number, len(match.group(1)), match.group(2)))
    return outline


def boundary_lines(outline: Outline) -> frozenset[int]:
    """Zeilen, an denen ein neuer Chunk beginnen soll (jede Überschrift)."""
    return frozenset(line for line, _level, _title in outline)


def section_path(outline: Outline, line: int) -> str | None:
    """Überschriftenpfad ("Kapitel > Abschnitt") für eine Zeile, None vor der ersten Überschrift."""
    stack: list[tuple[int, str]] = []
    for heading_line, level, title in outline:
        if heading_line > line:
            break
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
    return " > ".join(title for _level, title in stack) or None
