"""
parser/cobol/xref.py
=======================
F-025: Verwendungsstellen-XREF Datenfeld↔Paragraph. Wort-Match jedes WORD-
Tokens der PROCEDURE DIVISION gegen den Namensindex der `DataItem`s aus
data_division.py — kein Verb-Filter (MOVE/IF/COMPUTE/ADD/…) nötig, weil COBOL
reservierte Wörter nie gleichzeitig gültige Datennamen sein können: trifft ein
WORD-Token einen Item-Namen, ist es per Sprachdefinition eine echte
Feld-Referenz, keine Anweisung.

Zusätzlich zu den lokalen `DataItem`s kann der Scan die Felder der durch COPY
eindeutig ausgewählten Copybooks übernehmen (E-2). Das Ziel wird dabei mit
Copybook-Pfad und qualified_name festgehalten, damit die DB-Nachauflösung nie
allein über einen quellenweit häufigen Feldnamen raten muss.

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


def scan(
    program: CobolProgram,
    tokens: list[Token],
    items: list[DataItem],
    inherited_fields: list[dict] | None = None,
) -> tuple[list[ParsedEdge], list[str]]:
    errors: list[str] = []
    edges: list[ParsedEdge] = []

    procedure_division = next((d for d in program.divisions if d.name == "PROCEDURE"), None)
    if procedure_division is None:
        errors.append("Keine PROCEDURE DIVISION gefunden - USES-Kanten nicht durchsucht.")
        return edges, errors
    if not items and not inherited_fields:
        return edges, errors

    index = build_index(items)
    for field in inherited_fields or []:
        if field["name"].upper() != "FILLER":
            index.setdefault(field["effective_name"].upper(), []).append(field)
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

        meta = {}
        if target is not None:
            if isinstance(target, dict):
                meta = {
                    "copybook_path": target["path"],
                    "target_qualified_name": target["qualified_name"],
                }
            elif target.parent:
                meta = {"parent": target.parent}

        edges.append(
            ParsedEdge(
                type="USES",
                src_name=_enclosing_paragraph(program, tok.phys_line),
                dst_name=(target["name"] if isinstance(target, dict) else target.name) if target is not None else tok.value,
                resolution=resolution,
                src_start_line=tok.phys_line,
                src_end_line=tok.phys_line,
                scope=program.name,
                # target.parent überträgt die zur Parse-Zeit getroffene Disambiguierung
                # (z.B. per OF/IN) an die Persistenz weiter - ohne das könnte persist.py
                # bei mehreren gleichnamigen Datenfeldern im selben Programm nicht mehr
                # rekonstruieren, welches der xref-Resolver tatsächlich gemeint hat
                # (siehe 06_data_qualified.cbl).
                meta=meta,
            )
        )

    return edges, errors


def _resolve(candidates: list, proc_tokens: list[Token], idx: int, n: int) -> tuple[object | None, str]:
    if len(candidates) == 1:
        return candidates[0], "resolved"

    qualifier = _qualifier_after(proc_tokens, idx, n)
    if qualifier is not None:
        matches = [
            c for c in candidates
            if ((c.get("effective_parent") if isinstance(c, dict) else c.parent) or "").upper() == qualifier
        ]
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
