"""
parser/cobol/procedure.py
============================
F-023/024: CALL/PERFORM/GO TO als Kanten aus der PROCEDURE DIVISION.

Läuft nach divisions.scan() — braucht dessen CobolProgram (für die
Paragraphen-/Sections-Zeilenbereiche, zur lokalen Auflösung von PERFORM/GO TO)
sowie denselben Token-Strom noch einmal (nur der PROCEDURE-DIVISION-Ausschnitt
wird durchsucht).

Auflösung nach docs/ENTSCHEIDUNGEN.md E-1: PERFORM und GO TO sind
programmlokal und deshalb schon hier auflösbar (resolution="resolved", sobald
das Ziel unter den Paragraphen-/Section-Namen desselben Programms auftaucht).
CALL ist global (Ziel typischerweise ein anderes Programm/eine andere Datei)
und bleibt "unresolved" bzw. "dynamic" (Variable statt Literal) — die
Auflösung passiert erst im Nachlauf-Pass (Plan §6.4 Pass 2).
"""

from __future__ import annotations

from .lexer import Token
from .model import CobolProgram, ParsedEdge

_PERFORM_INLINE_KEYWORDS = {"UNTIL", "VARYING", "WITH", "TEST", "FOREVER"}


def scan(program: CobolProgram, tokens: list[Token]) -> tuple[list[ParsedEdge], list[str]]:
    errors: list[str] = []
    edges: list[ParsedEdge] = []

    procedure_division = next((d for d in program.divisions if d.name == "PROCEDURE"), None)
    if procedure_division is None:
        errors.append("Keine PROCEDURE DIVISION gefunden - CALL/PERFORM/GO TO nicht durchsucht.")
        return edges, errors

    local_names = {p.name.upper() for p in program.paragraphs} | {s.name.upper() for s in program.sections}

    proc_tokens = [
        t for t in tokens if procedure_division.start_line <= t.phys_line <= procedure_division.end_line
    ]
    n = len(proc_tokens)

    i = 0
    while i < n:
        tok = proc_tokens[i]
        nxt = proc_tokens[i + 1] if i + 1 < n else None

        if tok.kind == "WORD" and tok.value.upper() == "CALL":
            if nxt is not None and nxt.kind in ("LITERAL", "WORD"):
                dynamic = nxt.kind == "WORD"
                edges.append(
                    ParsedEdge(
                        type="CALL",
                        src_name=_enclosing_paragraph(program, tok.phys_line),
                        dst_name=_clean_name(nxt.value),
                        resolution="dynamic" if dynamic else "unresolved",
                        src_start_line=tok.phys_line,
                        src_end_line=_statement_end_line(proc_tokens, i + 1, nxt.phys_line),
                        scope=None,
                    )
                )
            i += 1
            continue

        if tok.kind == "WORD" and tok.value.upper() == "PERFORM":
            if nxt is not None and nxt.kind == "WORD" and nxt.value.upper() not in _PERFORM_INLINE_KEYWORDS:
                end_idx = i + 1
                meta: dict = {}
                thru_idx = i + 2
                if (
                    thru_idx < n
                    and proc_tokens[thru_idx].kind == "WORD"
                    and proc_tokens[thru_idx].value.upper() in ("THRU", "THROUGH")
                    and thru_idx + 1 < n
                    and proc_tokens[thru_idx + 1].kind == "WORD"
                ):
                    meta["thru"] = proc_tokens[thru_idx + 1].value
                    end_idx = thru_idx + 1
                resolved = nxt.value.upper() in local_names
                edges.append(
                    ParsedEdge(
                        type="PERFORM",
                        src_name=_enclosing_paragraph(program, tok.phys_line),
                        dst_name=nxt.value,
                        resolution="resolved" if resolved else "unresolved",
                        src_start_line=tok.phys_line,
                        src_end_line=_statement_end_line(proc_tokens, end_idx, proc_tokens[end_idx].phys_line),
                        scope=program.name,
                        meta=meta,
                    )
                )
            i += 1
            continue

        if tok.kind == "WORD" and tok.value.upper() == "GO" and _word_at(proc_tokens, i + 1, "TO"):
            j = i + 2
            targets: list[Token] = []
            while j < n and proc_tokens[j].kind == "WORD" and proc_tokens[j].value.upper() != "DEPENDING":
                targets.append(proc_tokens[j])
                j += 1
            end_line = _statement_end_line(proc_tokens, i + 2, tok.phys_line)
            src = _enclosing_paragraph(program, tok.phys_line)
            for t in targets:
                resolved = t.value.upper() in local_names
                edges.append(
                    ParsedEdge(
                        type="GOTO",
                        src_name=src,
                        dst_name=t.value,
                        resolution="resolved" if resolved else "unresolved",
                        src_start_line=tok.phys_line,
                        src_end_line=end_line,
                        scope=program.name,
                    )
                )
            i = j
            continue

        i += 1

    return edges, errors


def _enclosing_paragraph(program: CobolProgram, line: int) -> str:
    for p in program.paragraphs:
        if p.start_line <= line <= p.end_line:
            return p.name
    return ""


def _word_at(tokens: list[Token], idx: int, word: str) -> bool:
    return idx < len(tokens) and tokens[idx].kind == "WORD" and tokens[idx].value.upper() == word


def _statement_end_line(tokens: list[Token], start_idx: int, fallback_line: int) -> int:
    for j in range(start_idx, len(tokens)):
        if tokens[j].kind == "PERIOD":
            return tokens[j].phys_line
    return fallback_line


def _clean_name(value: str) -> str:
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
