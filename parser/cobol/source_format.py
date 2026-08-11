"""
parser/cobol/source_format.py
==============================
F-021: Fixed/Free-Autodetektion und Spaltenzerlegung.

Fixed Format (klassisches COBOL, Spalten 1-basiert):
    1-6   Sequenznummer-Bereich (ignoriert)
    7     Indikator: '*'/'/' = Kommentar, '-' = Continuation,
                      'D'/'d' = Debug-Zeile, '$' = Compiler-Direktive
    8-11  Area A   (Divisions, Sections, Paragraphnamen, FD/01-Level)
    12-72 Area B   (Anweisungen)
    73+   ignoriert (historisch Programmkennung)

Free Format: keine Spaltenbindung, Kommentar ab '*>' bis Zeilenende, keine
Continuation-Spalte (jede physische Zeile ist ihre eigene LogicalLine).

Diese Stufe ist bewusst kein vollständiger Standard-Parser, sondern deckt
genau das ab, was gegen den Testkorpus (parser/tests/cobol_corpus/)
verifiziert ist. Dialekt-Eigenheiten (Compiler-Direktiven, Debug-Modus,
Wort-Continuation außerhalb von Literalen) werden nachgezogen, sobald ein
realer COBOL-Bestand vorliegt (docs/UMSETZUNGSSTAND.md, „Fachlich offen").
"""

from __future__ import annotations

from .model import LogicalLine, Segment, SourceFormat

AREA_A_START = 7  # 0-basiert = Spalte 8
AREA_B_START = 11  # 0-basiert = Spalte 12
CODE_END = 72  # 0-basiert, exklusiv = nach Spalte 72

_COMMENT_INDICATORS = "*/"
_DEBUG_INDICATORS = "Dd"
_CONTINUATION_INDICATOR = "-"
_DIRECTIVE_INDICATORS = "$"
_QUOTES = ("'", '"')


def detect_format(text: str) -> SourceFormat:
    """Heuristische Fixed/Free-Erkennung (F-021).

    Stärkstes Signal für Free-Format: Inline-Kommentar '*>' oder Text in den
    Spalten 1-6, der keine Sequenznummer ist (im Fixed-Format wäre das
    entweder Ziffern oder Leerraum — Free-Format-Quellen fangen Divisions
    dagegen oft in Spalte 1 an). Stärkstes Signal für Fixed-Format: ein
    gültiger Indikator in Spalte 7.
    """
    fixed_signals = 0
    free_signals = 0
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if "*>" in raw:
            free_signals += 1
            continue
        seq_area = raw[:6]
        if seq_area.strip() and not seq_area.strip().isdigit():
            free_signals += 1
            continue
        indicator = raw[6] if len(raw) > 6 else ""
        if indicator and indicator in (
            _COMMENT_INDICATORS + _DEBUG_INDICATORS + _CONTINUATION_INDICATOR + _DIRECTIVE_INDICATORS
        ):
            fixed_signals += 1
    return "free" if free_signals > fixed_signals else "fixed"


def split_logical_lines(text: str, fmt: SourceFormat) -> list[LogicalLine]:
    if fmt == "free":
        return _split_free(text)
    return _split_fixed(text)


def _split_fixed(text: str) -> list[LogicalLine]:
    lines: list[LogicalLine] = []
    current: LogicalLine | None = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        indicator = raw[6] if len(raw) > 6 else " "
        code = raw[AREA_A_START:CODE_END]

        if indicator in _COMMENT_INDICATORS:
            lines.append(LogicalLine(lineno, lineno, [], "fixed", is_comment=True))
            current = None
            continue
        if indicator in _DEBUG_INDICATORS:
            lines.append(LogicalLine(lineno, lineno, [], "fixed", is_comment=True, is_debug=True))
            current = None
            continue
        if indicator in _DIRECTIVE_INDICATORS:
            lines.append(LogicalLine(lineno, lineno, [], "fixed", is_comment=True))
            current = None
            continue

        if not code.strip():
            # Leerzeile (ggf. mit Sequenznummer) — bricht eine laufende
            # Continuation nicht künstlich ab, trägt aber nichts bei.
            continue

        leading = len(code) - len(code.lstrip(" "))
        content = code.strip()
        col_start = AREA_A_START + leading

        if indicator == _CONTINUATION_INDICATOR and current is not None:
            open_quote = _open_literal_quote(current.text)
            if open_quote and content.startswith(open_quote):
                content = content[1:]
                col_start += 1
            current.segments.append(Segment(lineno, col_start, content))
            current.phys_end_line = lineno
            continue

        current = LogicalLine(lineno, lineno, [Segment(lineno, col_start, content)], "fixed")
        lines.append(current)

    return lines


def _split_free(text: str) -> list[LogicalLine]:
    lines: list[LogicalLine] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        # Compiler-Direktiven (`>>SOURCE FORMAT FREE`, `>>IF`/`>>DEFINE`, ...)
        # sind kein `*>`-Kommentar und keine gültige COBOL85-Anweisung — ohne
        # diesen Filter landet z.B. ">>SOURCE FORMAT FREE" als normale
        # LogicalLine im Baum und lässt die ANTLR-Grammatik direkt an der
        # ersten Zeile scheitern (Kein Division/PROGRAM-ID erkannt, siehe
        # divisions.py). Wie `_DIRECTIVE_INDICATORS` im Fixed-Format: die
        # Direktive wird nicht ausgewertet, nur unschädlich gemacht (F-021 -
        # "Dialekt-Eigenheiten werden nachgezogen").
        if raw.lstrip().startswith(">>"):
            lines.append(LogicalLine(lineno, lineno, [], "free", is_comment=True))
            continue

        marker = raw.find("*>")
        code = raw if marker == -1 else raw[:marker]

        if not code.strip():
            if marker != -1 and raw.strip():
                lines.append(LogicalLine(lineno, lineno, [], "free", is_comment=True))
            continue

        leading = len(code) - len(code.lstrip(" \t"))
        content = code.strip()
        lines.append(LogicalLine(lineno, lineno, [Segment(lineno, leading, content)], "free"))
    return lines


def _open_literal_quote(text: str) -> str | None:
    """Endet `text` mit einer ungeschlossenen Literal-Kette? Vereinfachte
    Heuristik: ungerade Anzahl eines Anführungszeichen-Typs gilt als offen.
    Erfasst keine verschachtelten Wechsel zwischen ' und " in einem Literal.
    """
    for quote in _QUOTES:
        if text.count(quote) % 2 == 1:
            return quote
    return None
