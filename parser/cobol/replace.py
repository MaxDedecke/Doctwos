"""
parser/cobol/replace.py
==========================
O-136: globales `REPLACE`/`REPLACE OFF` (nicht an ein COPY gebunden) als
Vorverarbeitungsschritt auf `LogicalLine`-Ebene, VOR dem Lexen/AST-Bau —
sowohl der eigene Tokenizer (lexer.py) als auch der ANTLR-Baum
(antlr_bridge.py, aus rekonstruiertem Text derselben LogicalLines) sehen
dadurch automatisch das substituierte Ergebnis, ohne dass divisions.py/
data_division.py/procedure.py/xref.py/copybook.py etwas davon wissen
müssen — dieselbe Vorverarbeitungsarchitektur wie conditional.py
(>>IF/>>DEFINE) und embedded.py (EXEC-Blöcke). Läuft NACH conditional.py
(ein `REPLACE` in einem sicher inaktiven `>>IF`-Zweig bleibt wirkungslos,
weil dessen Zeilen dann schon `is_comment=True` sind) und VOR embedded.py
(REPLACE gilt laut COBOL85 auch für eingebetteten SQL/CICS-Text, nicht nur
COBOL-Code selbst).

`REPLACE [LEADING|TRAILING] pseudo-1 BY pseudo-2 [, ...] .` bleibt ab der
FOLGEZEILE aktiv, bis das nächste `REPLACE`/`REPLACE OFF` es ablöst (nicht
additiv — dieselbe "letzte Regel gewinnt"-Semantik wie COBOL85 selbst) oder
die Datei endet. Die Anweisung selbst wird wie ein EXEC-Block unsichtbar
gemacht (Leerraum statt Text) — sie hat keine eigene Entity, anders als
EXEC SQL/CICS.

Bewusst eingegrenzter Umfang (kein Vorbau auf Vorrat, siehe Abnahme):
- Pseudotext-Operanden werden nur INNERHALB EINES Segments (einer
  physischen Zeile) gesucht, nicht über Continuation-Zeilen hinweg — ein
  Pseudotext, der sich über mehrere Zeilen erstreckt, bleibt unverändert
  (seltener Fall; dokumentierte Einschränkung statt Ratelösung).
- Ersetzung geschieht wortgrenzenbasiert (\\b) außerhalb von Literalen —
  angezeigter Literalinhalt wird nie verändert.
- `REPLACE`, das auf derselben physischen/logischen Zeile wie nachfolgender
  Code steht (unüblicher Stil), maskiert diese Zeile komplett — dieselbe
  Zeilen-statt-Spalten-Granularität wie embedded.py.
- Zeilennummern bleiben unverändert (CLAUDE.md); Spaltenpositionen können
  sich innerhalb einer betroffenen Zeile verschieben, wenn die Ersetzung
  eine andere Länge hat — das betrifft nur die interne Struktur-Erkennung,
  nie den angezeigten Originaltext (chunking.py nutzt weiterhin
  `text.splitlines()`, nicht diese transformierten Segmente).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace as _dc_replace

from . import lexer as lexer_mod
from .lexer import Token
from .model import LogicalLine, Segment
from .names import canonical_identifier

_OPERAND_KINDS = ("PSEUDO_TEXT", "LITERAL", "WORD")
_QUALIFIERS = ("LEADING", "TRAILING")
_LITERAL_RE = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")


@dataclass(frozen=True)
class _Pair:
    old: str
    new: str
    mode: str  # "plain" | "leading" | "trailing"


@dataclass(frozen=True)
class _Statement:
    start_line: int
    end_line: int
    pairs: tuple[_Pair, ...]  # leer bei REPLACE OFF


def apply(lines: list[LogicalLine]) -> list[LogicalLine]:
    tokens = lexer_mod.tokenize(lines)
    statements = _find_statements(tokens)
    if not statements:
        return lines

    masked_lines: set[int] = set()
    # (Zeile der REPLACE-Anweisung EXKLUSIV, naechste Anweisung EXKLUSIV, Paare)
    regions: list[tuple[int, int | None, tuple[_Pair, ...]]] = []
    for idx, stmt in enumerate(statements):
        for phys_line in range(stmt.start_line, stmt.end_line + 1):
            masked_lines.add(phys_line)
        region_end = statements[idx + 1].start_line if idx + 1 < len(statements) else None
        if stmt.pairs:
            regions.append((stmt.end_line, region_end, stmt.pairs))

    result: list[LogicalLine] = []
    for line in lines:
        if line.is_comment:
            result.append(line)
            continue
        if any(seg.phys_line in masked_lines for seg in line.segments):
            result.append(_dc_replace(line, segments=[_blank(seg) for seg in line.segments]))
            continue

        pairs = _active_pairs(line.phys_start_line, regions)
        if pairs is None:
            result.append(line)
            continue
        new_segments = [_substitute_segment(seg, pairs) for seg in line.segments]
        result.append(
            _dc_replace(line, segments=new_segments) if new_segments != line.segments else line
        )

    return result


def _find_statements(tokens: list[Token]) -> list[_Statement]:
    statements: list[_Statement] = []
    n = len(tokens)
    i = 0
    while i < n:
        tok = tokens[i]
        if not (tok.kind == "WORD" and canonical_identifier(tok.value) == "REPLACE"):
            i += 1
            continue

        j = i + 1
        if j < n and tokens[j].kind == "WORD" and canonical_identifier(tokens[j].value) == "OFF":
            end_idx = _find_period(tokens, j + 1)
        else:
            pairs: list[_Pair] = []
            while True:
                pair, j = _parse_pair(tokens, j)
                if pair is None:
                    break
                pairs.append(pair)
            end_idx = _find_period(tokens, j)
            if pairs:
                end_line = tokens[end_idx].phys_line if end_idx is not None else tok.phys_line
                statements.append(_Statement(tok.phys_line, end_line, tuple(pairs)))
            i = end_idx + 1 if end_idx is not None else n
            continue

        end_line = tokens[end_idx].phys_line if end_idx is not None else tok.phys_line
        statements.append(_Statement(tok.phys_line, end_line, ()))
        i = end_idx + 1 if end_idx is not None else n

    return statements


def _parse_pair(tokens: list[Token], j: int) -> tuple[_Pair | None, int]:
    """Ein `[LEADING|TRAILING] operand-1 BY operand-2`-Paar, oder
    (None, j unveraendert), falls an Position j kein vollstaendiges Paar
    mehr beginnt (dieselbe Konvention wie copybook.py::_replacing_pair)."""
    start = j
    n = len(tokens)
    mode = "plain"
    if j < n and tokens[j].kind == "WORD" and canonical_identifier(tokens[j].value) in _QUALIFIERS:
        mode = canonical_identifier(tokens[j].value).lower()
        j += 1
    if j >= n or tokens[j].kind not in _OPERAND_KINDS:
        return None, start
    operand1 = _clean_operand(tokens[j].value)
    j += 1
    if j >= n or not (tokens[j].kind == "WORD" and canonical_identifier(tokens[j].value) == "BY"):
        return None, start
    j += 1
    if j >= n or tokens[j].kind not in _OPERAND_KINDS:
        return None, start
    operand2 = _clean_operand(tokens[j].value)
    j += 1
    if not operand1:
        return None, start
    return _Pair(operand1, operand2, mode), j


def _active_pairs(
    phys_start_line: int, regions: list[tuple[int, int | None, tuple[_Pair, ...]]]
) -> tuple[_Pair, ...] | None:
    for region_start, region_end, pairs in regions:
        if phys_start_line > region_start and (region_end is None or phys_start_line < region_end):
            return pairs
    return None


def _substitute_segment(seg: Segment, pairs: tuple[_Pair, ...]) -> Segment:
    new_text = seg.text
    for pair in pairs:
        new_text = _substitute_outside_literals(new_text, pair)
    return seg if new_text == seg.text else Segment(seg.phys_line, seg.col_start, new_text)


def _pattern_for(pair: _Pair) -> re.Pattern[str]:
    """Wortgrenze (`\\b`) nur dort, wo das Operand-Ende selbst ein Wortzeichen
    ist - ein Pseudotext wie `:TAG:` ist durch die Doppelpunkte bereits
    selbst-abgrenzend, `\\b` fände dort (Uebergang Nicht-Wort -> Nicht-Wort)
    nie eine Grenze und die Ersetzung würde nie zünden."""
    old = pair.old
    need_lead = pair.mode != "trailing"
    need_trail = pair.mode != "leading"
    lead = r"\b" if need_lead and re.match(r"\w", old[0]) else ""
    trail = r"\b" if need_trail and re.match(r"\w", old[-1]) else ""
    return re.compile(lead + re.escape(old) + trail, re.IGNORECASE)


def _substitute_outside_literals(text: str, pair: _Pair) -> str:
    pattern = _pattern_for(pair)

    out: list[str] = []
    last = 0
    for m in _LITERAL_RE.finditer(text):
        out.append(pattern.sub(pair.new, text[last : m.start()]))
        out.append(text[m.start() : m.end()])  # Literalinhalt bleibt unangetastet
        last = m.end()
    out.append(pattern.sub(pair.new, text[last:]))
    return "".join(out)


def _blank(seg: Segment) -> Segment:
    return Segment(seg.phys_line, seg.col_start, " " * len(seg.text))


def _find_period(tokens: list[Token], start_idx: int) -> int | None:
    for j in range(start_idx, len(tokens)):
        if tokens[j].kind == "PERIOD":
            return j
    return None


def _clean_operand(value: str) -> str:
    if value.startswith("==") and value.endswith("=="):
        return value[2:-2].strip()
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
