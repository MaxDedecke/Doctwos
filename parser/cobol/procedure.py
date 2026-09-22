"""
parser/cobol/procedure.py
============================
F-023/024: CALL/PERFORM/GO TO als Kanten aus der PROCEDURE DIVISION, sowie
ENTRY-Anweisungen (O-138) als `program.entry_points`.

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

O-138: `program` ist bei mehreren bzw. verschachtelten Programmen pro Datei
ausschließlich EIN CobolProgram mit seinen eigenen Paragraphen/Sections -
`meta["program"]` trägt den Programmnamen zusätzlich auf jeder Kante mit, weil
`structure_persist.py` bei gleichnamigen Paragraphen/Feldern verschiedener
Programme derselben Datei sonst nicht mehr zwischen ihnen unterscheiden kann
(reine Namensgleichheit über `by_name`, ohne Programmzugehörigkeit).
"""

from __future__ import annotations

from .lexer import Token
from .model import CobolProgram, EntryPoint, ParsedEdge
from .names import canonical_identifier

_PERFORM_INLINE_KEYWORDS = {"UNTIL", "VARYING", "WITH", "TEST", "FOREVER"}


def scan(program: CobolProgram, tokens: list[Token]) -> tuple[list[ParsedEdge], list[str]]:
    errors: list[str] = []
    edges: list[ParsedEdge] = []

    procedure_division = next((d for d in program.divisions if d.name == "PROCEDURE"), None)
    if procedure_division is None:
        errors.append("Keine PROCEDURE DIVISION gefunden - CALL/PERFORM/GO TO nicht durchsucht.")
        return edges, errors

    local_targets: dict[str, list[str]] = {}
    for local in [*program.paragraphs, *program.sections]:
        local_targets.setdefault(canonical_identifier(local.name), []).append(local.name)

    proc_tokens = [
        t
        for t in tokens
        if procedure_division.start_line <= t.phys_line <= procedure_division.end_line
    ]
    n = len(proc_tokens)

    i = 0
    while i < n:
        tok = proc_tokens[i]
        nxt = proc_tokens[i + 1] if i + 1 < n else None

        if tok.kind == "WORD" and canonical_identifier(tok.value) == "CALL":
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
                        meta={"program": program.name},
                    )
                )
            i += 1
            continue

        if (
            tok.kind == "WORD"
            and canonical_identifier(tok.value) == "ENTRY"
            and nxt is not None
            and nxt.kind == "LITERAL"
        ):
            # O-138: alternativer Eintrittspunkt - dem umschließenden Programm
            # zuzuordnen ist der eigentliche Zweck dieses Zweigs (Abnahme
            # "ENTRY ist dem korrekten Programm zugeordnet"); eine globale
            # CALL-Auflösung auf ENTRY-Namen ist bewusst nicht Teil dieses
            # Tickets (edge_resolver.py kennt bislang nur "program").
            end_line = _statement_end_line(proc_tokens, i + 1, nxt.phys_line)
            program.entry_points.append(
                EntryPoint(
                    name=_clean_name(nxt.value),
                    paragraph=_enclosing_paragraph(program, tok.phys_line) or None,
                    start_line=tok.phys_line,
                    end_line=end_line,
                )
            )
            i += 1
            continue

        if tok.kind == "WORD" and canonical_identifier(tok.value) == "PERFORM":
            if (
                nxt is not None
                and nxt.kind == "WORD"
                and canonical_identifier(nxt.value) not in _PERFORM_INLINE_KEYWORDS
            ):
                end_idx = i + 1
                meta: dict = {"program": program.name}
                thru_idx = i + 2
                if (
                    thru_idx < n
                    and proc_tokens[thru_idx].kind == "WORD"
                    and canonical_identifier(proc_tokens[thru_idx].value) in ("THRU", "THROUGH")
                    and thru_idx + 1 < n
                    and proc_tokens[thru_idx + 1].kind == "WORD"
                ):
                    thru_name = proc_tokens[thru_idx + 1].value
                    meta["thru"] = thru_name
                    thru_targets = local_targets.get(canonical_identifier(thru_name), [])
                    if len(thru_targets) == 1:
                        meta["thru_resolution"] = "resolved"
                        meta["thru_target_qualified_name"] = f"{program.name}.{thru_targets[0]}"
                    else:
                        # An endpoint is informative even if it cannot be
                        # unambiguously navigated; do not turn a same-named
                        # paragraph/section into an arbitrary destination.
                        meta["thru_resolution"] = "unresolved"
                    end_idx = thru_idx + 1
                resolved = len(local_targets.get(canonical_identifier(nxt.value), [])) == 1
                edges.append(
                    ParsedEdge(
                        type="PERFORM",
                        src_name=_enclosing_paragraph(program, tok.phys_line),
                        dst_name=nxt.value,
                        resolution="resolved" if resolved else "unresolved",
                        src_start_line=tok.phys_line,
                        src_end_line=_statement_end_line(
                            proc_tokens, end_idx, proc_tokens[end_idx].phys_line
                        ),
                        scope=program.name,
                        meta=meta,
                    )
                )
            i += 1
            continue

        if (
            tok.kind == "WORD"
            and canonical_identifier(tok.value) == "GO"
            and _word_at(proc_tokens, i + 1, "TO")
        ):
            j = i + 2
            targets: list[Token] = []
            while (
                j < n
                and proc_tokens[j].kind == "WORD"
                and canonical_identifier(proc_tokens[j].value) != "DEPENDING"
            ):
                targets.append(proc_tokens[j])
                j += 1
            end_line = _statement_end_line(proc_tokens, i + 2, tok.phys_line)
            src = _enclosing_paragraph(program, tok.phys_line)
            for t in targets:
                resolved = len(local_targets.get(canonical_identifier(t.value), [])) == 1
                edges.append(
                    ParsedEdge(
                        type="GOTO",
                        src_name=src,
                        dst_name=t.value,
                        resolution="resolved" if resolved else "unresolved",
                        src_start_line=tok.phys_line,
                        src_end_line=end_line,
                        scope=program.name,
                        meta={"program": program.name},
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
    return (
        idx < len(tokens)
        and tokens[idx].kind == "WORD"
        and canonical_identifier(tokens[idx].value) == word
    )


def _statement_end_line(tokens: list[Token], start_idx: int, fallback_line: int) -> int:
    for j in range(start_idx, len(tokens)):
        if tokens[j].kind == "PERIOD":
            return tokens[j].phys_line
    return fallback_line


def _clean_name(value: str) -> str:
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
