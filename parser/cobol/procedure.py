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

_STATEMENT_DELIMITERS = {
    # Scope terminators
    "ELSE",
    "END-IF",
    "END-PERFORM",
    "END-EVALUATE",
    "END-READ",
    "END-WRITE",
    "END-REWRITE",
    "END-DELETE",
    "END-START",
    "END-CALL",
    "END-COMPUTE",
    "END-ADD",
    "END-SUBTRACT",
    "END-MULTIPLY",
    "END-DIVIDE",
    "END-STRING",
    "END-UNSTRING",
    "END-SEARCH",
    "END-RETURN",
    "END-EXEC",
    "WHEN",
    "THEN",
    # Verbs / statement starters
    "ACCEPT",
    "ADD",
    "ALTER",
    "CALL",
    "CANCEL",
    "CLOSE",
    "COMPUTE",
    "CONTINUE",
    "DELETE",
    "DISPLAY",
    "DIVIDE",
    "ENTRY",
    "EVALUATE",
    "EXIT",
    "GO",
    "GOBACK",
    "IF",
    "INITIALIZE",
    "INSPECT",
    "MERGE",
    "MOVE",
    "MULTIPLY",
    "OPEN",
    "PERFORM",
    "READ",
    "RELEASE",
    "RETURN",
    "REWRITE",
    "SEARCH",
    "SET",
    "SORT",
    "START",
    "STOP",
    "STRING",
    "SUBTRACT",
    "UNSTRING",
    "WRITE",
    "EXEC",
}


_CLAUSE_MAX_TOKENS = 24
_LOOP_HEAD_WORDS = {"WITH", "TEST", "BEFORE", "AFTER"}


Chars = dict[tuple[int, int], str]


def _char_map(lines: list | None) -> Chars | None:
    """(physische Zeile, Spalte) -> Zeichen. Nötig, weil der Lexer Operatoren (=, >, <) nicht als Token führt."""
    if not lines:
        return None
    chars: Chars = {}
    for line in lines:
        for segment in line.segments:
            for offset, char in enumerate(segment.text):
                chars[(segment.phys_line, segment.col_start + offset)] = char
    return chars


def _clause_text(tokens: list[Token], start: int, chars: Chars | None = None) -> str:
    """Lesbarer Text ab ``start`` bis zum nächsten Statement oder Punkt.

    Für Bedingungen (``IF``/``WHEN``/``UNTIL``): Der Text steht als Evidenz an der
    Kante, damit die Ablaufansicht "wenn WS-A = 'Y'" statt nur "IF" zeigen kann.
    Mit ``chars`` bleiben Operatoren erhalten; ohne fällt er auf die Token-Werte zurück.
    """
    taken: list[Token] = []
    for token in tokens[start:start + _CLAUSE_MAX_TOKENS]:
        if token.kind == "PERIOD":
            break
        if token.kind == "WORD" and canonical_identifier(token.value) in _STATEMENT_DELIMITERS:
            break
        taken.append(token)
    if not taken:
        return ""
    if chars is None:
        return " ".join(token.value for token in taken)
    pieces: list[str] = []
    line = taken[0].phys_line
    first_col = taken[0].col
    end_col = first_col
    for token in taken:
        if token.phys_line != line:
            pieces.append("".join(chars.get((line, c), " ") for c in range(first_col, end_col)))
            line, first_col = token.phys_line, token.col
        end_col = token.col + len(token.value)
    pieces.append("".join(chars.get((line, c), " ") for c in range(first_col, end_col)))
    return " ".join(" ".join(pieces).split())


def _loop_of(tokens: list[Token], start: int, chars: Chars | None = None) -> dict[str, str] | None:
    """Schleifenkopf einer PERFORM-Anweisung ab ``start`` (Token nach dem Namen bzw. nach PERFORM)."""
    n = len(tokens)
    i = start
    while i < n and tokens[i].kind == "WORD" and canonical_identifier(tokens[i].value) in _LOOP_HEAD_WORDS:
        i += 1
    if i >= n:
        return None
    head = tokens[i]
    word = canonical_identifier(head.value) if head.kind == "WORD" else ""
    if word == "UNTIL":
        return {"kind": "UNTIL", "text": _clause_text(tokens, i + 1, chars)}
    if word == "VARYING":
        return {"kind": "VARYING", "text": _clause_text(tokens, i + 1, chars)}
    if word == "FOREVER":
        return {"kind": "FOREVER", "text": ""}
    if (
        i + 1 < n
        and tokens[i + 1].kind == "WORD"
        and canonical_identifier(tokens[i + 1].value) == "TIMES"
        and head.kind != "PERIOD"
    ):
        return {"kind": "TIMES", "text": head.value}
    return None


def _with_path(meta: dict, path_stack: list[dict[str, str]]) -> dict:
    if path_stack:
        meta["control_path"] = [dict(entry) for entry in path_stack]
    return meta


def scan(
    program: CobolProgram, tokens: list[Token], lines: list | None = None
) -> tuple[list[ParsedEdge], list[str]]:
    chars = _char_map(lines)
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
    control_stack: list[dict[str, str]] = []
    # Parallele, reichere Sicht auf den Kontrollfluss (Bedingungstext, Schleifen):
    # `control_context` bleibt als stabiler Vertrag unverändert, `control_path`
    # trägt zusätzlich, *unter welcher Bedingung* bzw. in welcher Schleife eine
    # Kante steht.
    path_stack: list[dict[str, str]] = []

    i = 0
    while i < n:
        tok = proc_tokens[i]
        nxt = proc_tokens[i + 1] if i + 1 < n else None

        if tok.kind == "PERIOD":
            control_stack.clear()
            path_stack.clear()
            i += 1
            continue

        if tok.kind == "WORD":
            w = canonical_identifier(tok.value)
            if w == "IF":
                control_stack.append({"type": "IF", "branch": "THEN"})
            elif w == "ELSE":
                if control_stack and control_stack[-1]["type"] == "IF":
                    control_stack[-1]["branch"] = "ELSE"
            elif w == "END-IF":
                if control_stack and control_stack[-1]["type"] == "IF":
                    control_stack.pop()
            elif w == "EVALUATE":
                control_stack.append({"type": "EVALUATE", "branch": "WHEN"})
            elif w == "END-EVALUATE":
                if control_stack and control_stack[-1]["type"] == "EVALUATE":
                    control_stack.pop()

            if w == "IF":
                path_stack.append({"type": "IF", "branch": "THEN", "condition": _clause_text(proc_tokens, i + 1, chars)})
            elif w == "ELSE":
                if path_stack and path_stack[-1]["type"] == "IF":
                    path_stack[-1]["branch"] = "ELSE"
            elif w == "END-IF":
                if path_stack and path_stack[-1]["type"] == "IF":
                    path_stack.pop()
            elif w == "EVALUATE":
                path_stack.append({"type": "EVALUATE", "branch": "WHEN", "subject": _clause_text(proc_tokens, i + 1, chars), "when": ""})
            elif w == "WHEN":
                # Ein nicht mit END-IF geschlossenes IF im vorigen WHEN-Zweig verwerfen.
                index = next((k for k in range(len(path_stack) - 1, -1, -1) if path_stack[k]["type"] == "EVALUATE"), None)
                if index is not None:
                    del path_stack[index + 1:]
                    path_stack[index]["when"] = _clause_text(proc_tokens, i + 1, chars)
            elif w == "END-EVALUATE":
                index = next((k for k in range(len(path_stack) - 1, -1, -1) if path_stack[k]["type"] == "EVALUATE"), None)
                if index is not None:
                    del path_stack[index:]
            elif w == "END-PERFORM":
                if path_stack and path_stack[-1]["type"] == "LOOP":
                    path_stack.pop()

        if tok.kind == "WORD" and canonical_identifier(tok.value) == "CALL":
            if nxt is not None and nxt.kind in ("LITERAL", "WORD"):
                dynamic = nxt.kind == "WORD"
                end_line = _statement_end_line(proc_tokens, i + 1, nxt.phys_line)
                meta = _with_path(_build_meta(program.name, control_stack), path_stack)
                edges.append(
                    ParsedEdge(
                        type="CALL",
                        src_name=_enclosing_paragraph(program, tok.phys_line),
                        dst_name=_clean_name(nxt.value),
                        resolution="dynamic" if dynamic else "unresolved",
                        src_start_line=tok.phys_line,
                        src_end_line=end_line,
                        scope=None,
                        meta=meta,
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
            # Check for inline perform
            is_inline = False
            if nxt is not None and nxt.kind == "WORD":
                nxt_canon = canonical_identifier(nxt.value)
                if nxt_canon in _PERFORM_INLINE_KEYWORDS or nxt_canon in _STATEMENT_DELIMITERS:
                    is_inline = True
                elif (
                    i + 2 < n
                    and proc_tokens[i + 2].kind == "WORD"
                    and canonical_identifier(proc_tokens[i + 2].value) == "TIMES"
                ):
                    # e.g. PERFORM TIMES-N TIMES (count variable followed by TIMES)
                    is_inline = True
            else:
                is_inline = True

            if is_inline:
                loop = _loop_of(proc_tokens, i + 1, chars)
                if loop is not None:
                    path_stack.append({"type": "LOOP", **loop})
                else:
                    # Reines PERFORM ... END-PERFORM: nur der END-PERFORM-Abgleich zählt.
                    path_stack.append({"type": "LOOP", "kind": "INLINE", "text": ""})

            if not is_inline and nxt is not None and nxt.kind == "WORD":
                end_idx = i + 1
                meta = _with_path(_build_meta(program.name, control_stack), path_stack)
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
                loop = _loop_of(proc_tokens, end_idx + 1, chars)
                if loop is not None:
                    meta["loop"] = loop
                resolved = len(local_targets.get(canonical_identifier(nxt.value), [])) == 1
                end_line = _statement_end_line(
                    proc_tokens, end_idx, proc_tokens[end_idx].phys_line
                )
                edges.append(
                    ParsedEdge(
                        type="PERFORM",
                        src_name=_enclosing_paragraph(program, tok.phys_line),
                        dst_name=nxt.value,
                        resolution="resolved" if resolved else "unresolved",
                        src_start_line=tok.phys_line,
                        src_end_line=end_line,
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
            # Scan ahead to see if DEPENDING is in this statement before the next statement delimiter
            k = j
            has_depending = False
            depending_idx = -1
            stmt_end_idx = j
            while k < n and proc_tokens[k].kind != "PERIOD":
                if proc_tokens[k].kind == "WORD":
                    cid = canonical_identifier(proc_tokens[k].value)
                    if cid == "DEPENDING":
                        has_depending = True
                        depending_idx = k
                    elif cid in _STATEMENT_DELIMITERS:
                        break
                stmt_end_idx = k
                k += 1

            targets: list[Token] = []
            if has_depending:
                for idx in range(j, depending_idx):
                    if (
                        proc_tokens[idx].kind == "WORD"
                        and canonical_identifier(proc_tokens[idx].value) not in _STATEMENT_DELIMITERS
                    ):
                        targets.append(proc_tokens[idx])
                end_line = _statement_end_line(
                    proc_tokens, depending_idx, proc_tokens[stmt_end_idx].phys_line
                )
                next_i = k
            else:
                if (
                    j < n
                    and proc_tokens[j].kind == "WORD"
                    and canonical_identifier(proc_tokens[j].value) not in _STATEMENT_DELIMITERS
                ):
                    targets.append(proc_tokens[j])
                    end_line = _statement_end_line(proc_tokens, j, proc_tokens[j].phys_line)
                    next_i = j + 1
                else:
                    end_line = tok.phys_line
                    next_i = j

            src = _enclosing_paragraph(program, tok.phys_line)
            meta = _with_path(_build_meta(program.name, control_stack), path_stack)
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
                        meta=dict(meta),
                    )
                )
            i = next_i
            continue

        i += 1

    return edges, errors


def _build_meta(
    program_name: str,
    control_stack: list[dict[str, str]],
    extra: dict | None = None,
) -> dict:
    meta: dict = {"program": program_name}
    if extra:
        meta.update(extra)
    if control_stack:
        meta["control_context"] = [dict(c) for c in control_stack]
    return meta


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
    last_line = fallback_line
    for j in range(start_idx, len(tokens)):
        t = tokens[j]
        if t.kind == "PERIOD":
            return t.phys_line
        if t.kind == "WORD" and canonical_identifier(t.value) in _STATEMENT_DELIMITERS:
            return last_line
        last_line = t.phys_line
    return last_line


def _clean_name(value: str) -> str:
    if value[:1] in ("'", '"') and value[-1:] == value[:1]:
        return value[1:-1]
    return value
