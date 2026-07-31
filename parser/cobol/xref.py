"""
parser/cobol/xref.py
=======================
F-025: Verwendungsstellen-XREF Datenfeld↔Paragraph. Wort-Match jedes WORD-
Tokens der PROCEDURE DIVISION gegen den Namensindex der `DataItem`s aus
data_division.py — kein Verb-Filter (MOVE/IF/COMPUTE/ADD/…) nötig, weil COBOL
reservierte Wörter nie gleichzeitig gültige Datennamen sein können: trifft ein
WORD-Token einen Item-Namen, ist es per Sprachdefinition eine echte
Feld-Referenz, keine Anweisung.

Diese erste Fassung indiziert nur die `DataItem`s **dieses Programms** —
docs/ENTSCHEIDUNGEN.md E-2 verlangt einen quellenweiten Index über
Copybook-Grenzen hinweg, der erst mit copybook.py/parse.py entsteht (offen
bis dahin, kein Blocker für dieses Teilstück).

Auflösung: genau ein Treffer im Index → resolved. Mehrere Treffer (derselbe
Feldname in unterschiedlichen Gruppen, s. 06_data_qualified.cbl) werden über
ein direkt folgendes OF/IN <Gruppe> disambiguiert; bleibt es mehrdeutig,
unresolved statt geraten (dieselbe Regel wie bei COPY … REPLACING in E-2).
Paragraphen-/Section-Namen werden aus dem Feldindex ausgeschlossen, sonst
würden PERFORM-/GO-TO-Ziele fälschlich als Datenfeld-Nutzung gezählt.
"""

from __future__ import annotations

from .lexer import Token
from .model import CobolProgram, DataItem, ParsedEdge

_QUALIFIERS = ("OF", "IN")


def build_index(items: list[DataItem]) -> dict[str, list[DataItem]]:
    index: dict[str, list[DataItem]] = {}
    for item in items:
        if item.name.upper() == "FILLER":
            continue
        index.setdefault(item.name.upper(), []).append(item)
    return index


def scan(program: CobolProgram, tokens: list[Token], items: list[DataItem]) -> tuple[list[ParsedEdge], list[str]]:
    errors: list[str] = []
    edges: list[ParsedEdge] = []

    procedure_division = next((d for d in program.divisions if d.name == "PROCEDURE"), None)
    if procedure_division is None:
        errors.append("Keine PROCEDURE DIVISION gefunden - USES-Kanten nicht durchsucht.")
        return edges, errors
    if not items:
        return edges, errors

    index = build_index(items)
    local_names = {p.name.upper() for p in program.paragraphs} | {s.name.upper() for s in program.sections}

    proc_tokens = [
        t for t in tokens if procedure_division.start_line <= t.phys_line <= procedure_division.end_line
    ]
    n = len(proc_tokens)

    for i, tok in enumerate(proc_tokens):
        if tok.kind != "WORD":
            continue
        key = tok.value.upper()
        if key in local_names or key not in index:
            continue

        candidates = index[key]
        target, resolution = _resolve(candidates, proc_tokens, i, n)

        edges.append(
            ParsedEdge(
                type="USES",
                src_name=_enclosing_paragraph(program, tok.phys_line),
                dst_name=target.name if target is not None else tok.value,
                resolution=resolution,
                src_start_line=tok.phys_line,
                src_end_line=tok.phys_line,
                scope=program.name,
            )
        )

    return edges, errors


def _resolve(
    candidates: list[DataItem], proc_tokens: list[Token], idx: int, n: int
) -> tuple[DataItem | None, str]:
    if len(candidates) == 1:
        return candidates[0], "resolved"

    qualifier = _qualifier_after(proc_tokens, idx, n)
    if qualifier is not None:
        matches = [c for c in candidates if c.parent is not None and c.parent.upper() == qualifier]
        if len(matches) == 1:
            return matches[0], "resolved"

    return None, "unresolved"


def _qualifier_after(proc_tokens: list[Token], idx: int, n: int) -> str | None:
    nxt = proc_tokens[idx + 1] if idx + 1 < n else None
    if nxt is None or nxt.kind != "WORD" or nxt.value.upper() not in _QUALIFIERS:
        return None
    q_tok = proc_tokens[idx + 2] if idx + 2 < n else None
    if q_tok is None or q_tok.kind != "WORD":
        return None
    return q_tok.value.upper()


def _enclosing_paragraph(program: CobolProgram, line: int) -> str:
    for p in program.paragraphs:
        if p.start_line <= line <= p.end_line:
            return p.name
    return ""
