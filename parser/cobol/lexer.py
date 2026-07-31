"""
parser/cobol/lexer.py
======================
Tokenizer über LogicalLines: Wörter, Literale, Nummern, Satzenden (.),
Area A/B-Position, Pseudo-Text (== ==) für COPY … REPLACING.

Läuft nach embedded.mask() — EXEC-Blöcke sind zu diesem Zeitpunkt bereits
durch satzzeichenfreie Platzhalter ersetzt, ein Punkt im Quelltext ist hier
also immer ein echtes Satzende oder eine Dezimalstelle, nie SQL-Syntax.

Tokenisiert pro Segment (nicht pro verketteter LogicalLine), damit die
Spaltenposition jedes Tokens exakt bleibt. Bekannte Grenze: ein normales Wort
(kein Literal), das über eine Continuation-Zeile hinweg gebrochen wird,
zerfällt in zwei Tokens — dieser Fall ist in der Praxis selten (Continuation
dient primär langen Literalen/PICTURE-Klauseln) und im Testkorpus nicht
abgedeckt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model import LogicalLine, Segment, SourceFormat
from .source_format import AREA_B_START

_TOKEN_RE = re.compile(
    r"""
      (?P<PSEUDO_TEXT>==[^=]*==)
    | (?P<LITERAL>'(?:[^']|'')*'|"(?:[^"]|"")*")
    | (?P<NUMBER>\d+(?:\.\d+)?(?![A-Za-z\-]))
    | (?P<WORD>[A-Za-z0-9][A-Za-z0-9\-]*)
    | (?P<PERIOD>\.)
    """,
    re.VERBOSE,
)


@dataclass
class Token:
    kind: str
    value: str
    phys_line: int
    col: int
    area: str | None


def tokenize(lines: list[LogicalLine]) -> list[Token]:
    tokens: list[Token] = []
    for line in lines:
        if line.is_comment:
            continue
        for seg in line.segments:
            tokens.extend(_tokenize_segment(seg, line.source_format))
    return tokens


def _tokenize_segment(seg: Segment, fmt: SourceFormat) -> list[Token]:
    out: list[Token] = []
    for m in _TOKEN_RE.finditer(seg.text):
        col = seg.col_start + m.start()
        area = None
        if fmt == "fixed":
            area = "A" if col < AREA_B_START else "B"
        out.append(Token(m.lastgroup, m.group(), seg.phys_line, col, area))
    return out
