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

from .model import LogicalLine, Segment, SourceFormat
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
