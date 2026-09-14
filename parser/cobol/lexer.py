"""
parser/cobol/lexer.py
======================
Tokenizer über LogicalLines: Wörter, Literale, Nummern, Satzenden (.),
Area A/B-Position, Pseudo-Text (== ==) für COPY … REPLACING.

Läuft nach embedded.mask() — EXEC-Blöcke sind zu diesem Zeitpunkt bereits
durch satzzeichenfreie Platzhalter ersetzt, ein Punkt im Quelltext ist hier
also immer ein echtes Satzende oder eine Dezimalstelle, nie SQL-Syntax.

Tokenisiert je LogicalLine, mit einer Zeichenpositionstabelle aus deren
Segmenten. Dadurch bleiben Spaltenpositionen exakt und ein Literal oder Wort,
das über eine Continuation-Zeile fortgesetzt wird, bleibt ein einzelnes Token.

SYMBOL deckt bewusst nur `(`/`)` ab — die einzigen PICTURE-Klausel-Zeichen,
die sonst stillschweigend aus dem Tokenstrom fallen würden (`_TOKEN_RE`
matcht nur, was ein `finditer` trifft; unbekannte Zeichen werden sonst
übersprungen). `data_division.py` rekonstruiert eine PIC-Klausel wie
`X(10)V99` durch lückenloses Aneinanderhängen der Token-Werte anhand ihrer
Spaltenposition — dafür müssen die Klammern als eigene Tokens auftauchen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model import LogicalLine
from .source_format import AREA_B_START

# WORD nutzt \w statt A-Za-z0-9, damit deutsche Bezeichner mit Umlauten/ß
# (z.B. Paragraph "020-DATEIEN-ÖFFNEN") ein einziges Token bleiben statt an
# jedem Umlaut aufzubrechen - Python-\w ist auf str-Pattern unicode-bewusst.
# [^\W_] ist "\w ohne _", weil COBOL-Bezeichner keinen Unterstrich kennen und
# das Verhalten sonst von A-Za-z0-9 (das _ ebenfalls ausschliesst) abweichen
# wuerde.
#
# NUMBER-Lookahead muss dieselbe Zeichenklasse (plus Bindestrich)
# ausschliessen: sonst backtrackt das gierige \d+ bei einem numerisch
# benannten Paragraphen wie "010-SYSTEMDATEN-LADEN" auf "01", weil die
# verbleibende "0" selbst kein Wortzeichen/- ist - der Rest
# "0-SYSTEMDATEN-LADEN" faellt dann als zweites WORD-Token an. Numerische
# Paragraphennamen sind COBOL-Konvention; der Bug zerriss praktisch jeden
# PERFORM/GOTO-Verweis und liess den Call-Graph ohne Kanten dastehen.
_TOKEN_RE = re.compile(
    r"""
      (?P<PSEUDO_TEXT>==[^=]*==)
    | (?P<LITERAL>'(?:[^']|'')*'|"(?:[^"]|"")*")
    | (?P<NUMBER>\d+(?:\.\d+)?(?![^\W_]|-))
    | (?P<WORD>[^\W_](?:[^\W_]|-)*)
    | (?P<PERIOD>\.)
    | (?P<SYMBOL>[()])
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
        tokens.extend(_tokenize_line(line))
    return tokens


def _tokenize_line(line: LogicalLine) -> list[Token]:
    text = "".join(seg.text for seg in line.segments)
    positions = [
        (seg.phys_line, seg.col_start + offset)
        for seg in line.segments
        for offset, _ in enumerate(seg.text)
    ]
    out: list[Token] = []
    for m in _TOKEN_RE.finditer(text):
        phys_line, col = positions[m.start()]
        area = None
        if line.source_format != "free":
            area = "A" if col < AREA_B_START else "B"
        out.append(Token(m.lastgroup, m.group(), phys_line, col, area))
    return out
