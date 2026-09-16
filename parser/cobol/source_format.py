"""COBOL-Quellformat: Erkennung, Direktiven und zeilentreue Zerlegung.

O-123 wertet ``>>SOURCE [FORMAT] [IS]`` aus, auch eingerückt. Eine
Direktive gilt ab der folgenden physischen Zeile; so bleiben gemischte
Fixed/Free-Dateien und ihre Originalpositionen nachvollziehbar.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .model import LogicalLine, Segment, SourceFormat
from .profile import SourceColumns

AREA_A_START = 7  # 0-basiert = Spalte 8
AREA_B_START = 11  # 0-basiert = Spalte 12
CODE_END = 72  # 0-basiert, exklusiv = nach Spalte 72

_COMMENT_INDICATORS = "*/"
_DEBUG_INDICATORS = "Dd"
_CONTINUATION_INDICATOR = "-"
_DIRECTIVE_INDICATORS = "$"
_QUOTES = ("'", '"')
_SOURCE_FORMAT_DIRECTIVE = re.compile(
    r"^>>\s*SOURCE(?:\s+FORMAT)?(?:\s+IS)?\s+(FIXED|FREE|VARIABLE|EXTENDED)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Layout:
    indicator_index: int
    area_a_start: int
    area_b_start: int
    code_end: int | None


def _layout_for(fmt: SourceFormat, columns: SourceColumns | None) -> _Layout:
    """Liefert 0-basierte Grenzen einer spaltengebundenen Quellzeile."""
    if columns is None:
        # Fixed: 72, Variable: 250 (Micro Focus/GnuCOBOL), Extended: 252
        # (IBM). Alle drei behalten die linken Fixed-Format-Spalten bei.
        end = {"fixed": 72, "variable": 250, "extended": 252}[fmt]
        return _Layout(6, AREA_A_START, AREA_B_START, end)
    return _Layout(
        columns.indicator_column - 1,
        columns.area_a_start - 1,
        columns.area_b_start - 1,
        columns.code_end,
    )


def _directive_format(text: str) -> SourceFormat | None:
    match = _SOURCE_FORMAT_DIRECTIVE.match(text.lstrip())
    return match.group(1).lower() if match else None


def initial_format_directive(text: str) -> SourceFormat | None:
    """Direktive vor dem ersten echten Quelltext, also ein Startformat."""
    for raw in text.splitlines():
        if not raw.strip():
            continue
        directive = _directive_format(raw)
        if directive is not None:
            return directive
        # Eine Fixed-/Variable-/Extended-Quelle kann die Direktive nach
        # Sequenz- und Indikatorbereich tragen (z. B. ``000100 >>SOURCE``).
        # Vor dem ersten Programmtext ist auch das eine explizite Vorgabe.
        directive = _directive_format(raw[AREA_A_START:CODE_END])
        if directive is not None:
            return directive
        return None
    return None


def detect_format(text: str) -> SourceFormat:
    """Ermittelt das Startformat; Direktiven schlagen die Heuristik.

    Ohne bestätigtes Profil und ohne anfängliche Direktive bleibt die frühere
    Fixed/Free-Heuristik ein gekennzeichneter Fallback (parse.py).
    """
    directive = initial_format_directive(text)
    if directive is not None:
        return directive

    fixed_signals = 0
    free_signals = 0
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if _without_inline_comment(raw) != raw:
            free_signals += 1
            continue
        seq_area = raw[:6]
        if seq_area.strip() and not seq_area.strip().isdigit():
            free_signals += 1
            continue
        indicator = raw[6] if len(raw) > 6 else ""
        if indicator and indicator in (
            _COMMENT_INDICATORS
            + _DEBUG_INDICATORS
            + _CONTINUATION_INDICATOR
            + _DIRECTIVE_INDICATORS
        ):
            fixed_signals += 1
    return "free" if free_signals > fixed_signals else "fixed"


def split_logical_lines(
    text: str,
    fmt: SourceFormat,
    columns: SourceColumns | None = None,
    debug_mode: bool = False,
) -> list[LogicalLine]:
    """Zerlegt im Startformat und folgt SOURCE-FORMAT-Wechseln.

    Das Format steht pro LogicalLine, nicht nur global. Dadurch erhalten
    Lexer und ANTLR die korrekte Area-A/B-Position selbst bei einem Wechsel
    innerhalb derselben Datei.
    """
    lines: list[LogicalLine] = []
    current: LogicalLine | None = None
    active_format = fmt

    for lineno, raw in enumerate(text.splitlines(), start=1):
        directive = _directive_in_line(raw, active_format, columns)
        if directive is not None:
            lines.append(LogicalLine(lineno, lineno, [], active_format, is_comment=True))
            current = None
            active_format = directive
            continue

        if active_format == "free":
            _append_free_line(lines, lineno, raw)
            current = None
        else:
            current = _append_columnar_line(
                lines, current, lineno, raw, active_format, columns, debug_mode
            )

    return lines


def _directive_in_line(
    raw: str, fmt: SourceFormat, columns: SourceColumns | None
) -> SourceFormat | None:
    if fmt == "free":
        return _directive_format(raw)
    layout = _layout_for(fmt, columns)
    return _directive_format(raw[layout.area_a_start : layout.code_end])


def _append_columnar_line(
    lines: list[LogicalLine],
    current: LogicalLine | None,
    lineno: int,
    raw: str,
    fmt: SourceFormat,
    columns: SourceColumns | None,
    debug_mode: bool,
) -> LogicalLine | None:
    # Fixed-format columns are display columns. Tabs before the code area
    # therefore advance to the next eight-column stop rather than counting
    # as one source column.
    raw = raw.expandtabs(8)
    layout = _layout_for(fmt, columns)
    indicator = raw[layout.indicator_index] if len(raw) > layout.indicator_index else " "
    code = raw[layout.area_a_start : layout.code_end]

    if indicator in _COMMENT_INDICATORS:
        lines.append(LogicalLine(lineno, lineno, [], fmt, is_comment=True))
        return None
    if indicator in _DEBUG_INDICATORS:
        if not debug_mode:
            lines.append(LogicalLine(lineno, lineno, [], fmt, is_comment=True, is_debug=True))
            return None
    if indicator in _DIRECTIVE_INDICATORS:
        lines.append(LogicalLine(lineno, lineno, [], fmt, is_comment=True, directive=code.strip()))
        return None
    if _is_compiler_directive(code):
        lines.append(LogicalLine(lineno, lineno, [], fmt, is_comment=True, directive=code.strip()))
        return None
    code = _without_inline_comment(code)
    if not code.strip():
        return current

    leading = len(code) - len(code.lstrip(" "))
    content = code.strip()
    col_start = layout.area_a_start + leading
    if indicator == _CONTINUATION_INDICATOR and current is not None:
        open_quote = _open_literal_quote(current.text)
        if open_quote and content.startswith(open_quote):
            content = content[1:]
            col_start += 1
        current.segments.append(Segment(lineno, col_start, content))
        current.phys_end_line = lineno
        return current

    current = LogicalLine(
        lineno,
        lineno,
        [Segment(lineno, col_start, content)],
        fmt,
        is_debug=indicator in _DEBUG_INDICATORS,
    )
    lines.append(current)
    return current


def _append_free_line(lines: list[LogicalLine], lineno: int, raw: str) -> None:
    # SOURCE-FORMAT wurde bereits vor diesem Aufruf ausgewertet. Andere
    # Präprozessor-Direktiven bleiben aus dem COBOL85-Strom. O-124 wertet die
    # dabei erhaltene ``directive``-Information vor Lexer/Parser sicher aus.
    if raw.lstrip().startswith(">>"):
        lines.append(
            LogicalLine(lineno, lineno, [], "free", is_comment=True, directive=raw.lstrip())
        )
        return
    if _is_compiler_directive(raw):
        lines.append(
            LogicalLine(lineno, lineno, [], "free", is_comment=True, directive=raw.lstrip())
        )
        return
    code = _without_inline_comment(raw)
    if not code.strip():
        if code != raw and raw.strip():
            lines.append(LogicalLine(lineno, lineno, [], "free", is_comment=True))
        return
    leading = len(code) - len(code.lstrip(" \t"))
    lines.append(LogicalLine(lineno, lineno, [Segment(lineno, leading, code.strip())], "free"))


def _split_fixed(text: str) -> list[LogicalLine]:
    """Kompatibilitätswrapper für direkte ältere Aufrufe."""
    return split_logical_lines(text, "fixed")


def _split_free(text: str) -> list[LogicalLine]:
    """Kompatibilitätswrapper für direkte ältere Aufrufe."""
    return split_logical_lines(text, "free")


def _open_literal_quote(text: str) -> str | None:
    """Endet ``text`` mit einer ungeschlossenen COBOL-Literal-Kette?"""
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote is None:
            if char in _QUOTES:
                quote = char
        elif char == quote:
            if index + 1 < len(text) and text[index + 1] == quote:
                index += 1
            else:
                quote = None
        index += 1
    return quote


def _without_inline_comment(text: str) -> str:
    """Schneidet ``*>`` nur außerhalb eines COBOL-Literals ab."""
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote is None:
            if char in _QUOTES:
                quote = char
            elif char == "*" and text[index + 1 : index + 2] == ">":
                return text[:index]
        elif char == quote:
            if index + 1 < len(text) and text[index + 1] == quote:
                index += 1
            else:
                quote = None
        index += 1
    return text


def _is_compiler_directive(text: str) -> bool:
    """Erkennt Compilerkarten, ohne deren Optionen selbst auszuführen."""
    return bool(re.match(r"^\s*(?:\$SET\b|CBL(?:\s|,|$)|PROCESS(?:\s|,|$))", text, re.I))
