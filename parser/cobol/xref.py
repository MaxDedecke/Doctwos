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
from .names import canonical_identifier

_QUALIFIERS = ("OF", "IN")
_ASSIGNMENT_VERBS = {
    "ACCEPT", "ADD", "COMPUTE", "DIVIDE", "INITIALIZE", "MOVE",
    "MULTIPLY", "READ", "SET", "SUBTRACT", "WRITE", "REWRITE",
}
_STATEMENT_VERBS = _ASSIGNMENT_VERBS | {
    "ACCEPT", "ALTER", "CALL", "CANCEL", "CLOSE", "CONTINUE", "DELETE",
    "DISPLAY", "ELSE", "END-ADD", "END-CALL", "END-COMPUTE", "END-DELETE",
    "END-DIVIDE", "END-EVALUATE", "END-IF", "END-MULTIPLY", "END-READ",
    "END-REWRITE", "END-SEARCH", "END-START", "END-SUBTRACT", "END-WRITE",
    "EVALUATE", "EXEC", "EXIT", "GO", "GOBACK", "GOTO", "IF", "INITIALIZE",
    "INSPECT", "MERGE", "OPEN", "PERFORM", "RELEASE", "RETURN", "SEARCH",
    "SORT", "START", "STOP", "THEN", "UNTIL", "WHEN",
}
_READ_CONTEXT_VERBS = {"DISPLAY", "EVALUATE", "IF", "UNTIL", "WHEN"}


def _reference_access(proc_tokens: list[Token], idx: int) -> tuple[str, str, str] | None:
    """Classify operand direction for common COBOL data operations."""
    start = idx
    while start >= 0:
        token = proc_tokens[start]
        word = canonical_identifier(token.value) if token.kind == "WORD" else ""
        if token.kind == "PERIOD" or word in _STATEMENT_VERBS:
            break
        start -= 1
    verb_token = proc_tokens[start] if start >= 0 else None
    verb = canonical_identifier(verb_token.value) if verb_token and verb_token.kind == "WORD" else ""
    if verb not in _ASSIGNMENT_VERBS | _READ_CONTEXT_VERBS:
        return None
    end = idx + 1
    while end < len(proc_tokens):
        token = proc_tokens[end]
        word = canonical_identifier(token.value) if token.kind == "WORD" else ""
        if token.kind == "PERIOD" or word in _STATEMENT_VERBS:
            break
        end += 1
    statement = proc_tokens[start:end]
    relative = idx - start
    words = [canonical_identifier(token.value) if token.kind == "WORD" else token.value for token in statement]
    markers = {word: [i for i, item in enumerate(words) if item == word] for word in (
        "TO", "FROM", "GIVING", "INTO", "BY", "UP", "DOWN", "TRUE", "FALSE",
    )}
    mode = None
    role = "operand"
    if verb == "MOVE":
        marker = next(iter(markers["TO"]), None)
        if marker is not None:
            mode, role = ("READS", "source") if relative < marker else ("WRITES", "target")
    elif verb in {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE"}:
        marker_word = {"ADD": "TO", "SUBTRACT": "FROM", "MULTIPLY": "BY", "DIVIDE": "INTO"}[verb]
        marker = next(iter(markers[marker_word]), None)
        giving = next(iter(markers["GIVING"]), None)
        if marker is not None:
            if relative < marker:
                mode, role = "READS", "source"
            elif giving is not None and relative > giving:
                mode, role = "WRITES", "result"
            elif giving is not None and relative > marker:
                mode, role = "READS", "source"
            else:
                mode, role = "READS_WRITES", "target"
    elif verb == "COMPUTE":
        equal = next((i for i, item in enumerate(words) if item == "="), None)
        if equal is not None:
            mode, role = ("WRITES", "result") if relative < equal else ("READS", "source")
    elif verb in {"ACCEPT", "INITIALIZE"}:
        mode, role = "WRITES", "target"
    elif verb == "READ":
        marker = next(iter(markers["INTO"]), None)
        if marker is not None and relative > marker:
            mode, role = "WRITES", "target"
    elif verb in {"WRITE", "REWRITE"}:
        marker = next(iter(markers["FROM"]), None)
        if marker is not None:
            mode, role = ("WRITES", "record") if relative < marker else ("READS", "source")
        else:
            mode, role = "WRITES", "record"
    elif verb == "SET":
        if markers["UP"] or markers["DOWN"]:
            by = next(iter(markers["BY"]), None)
            mode, role = ("READS_WRITES", "target") if by is None or relative < by else ("READS", "source")
        else:
            mode, role = "WRITES", "target"
    elif verb in _READ_CONTEXT_VERBS:
        mode, role = "READS", "condition" if verb != "DISPLAY" else "output"
    if mode == "READS_WRITES":
        return "READS_WRITES", role, verb
    return (mode, role, verb) if mode else None


def build_index(items: list[DataItem]) -> dict[str, list[DataItem]]:
    index: dict[str, list[DataItem]] = {}
    for item in items:
        if canonical_identifier(item.name) == "FILLER":
            continue
        index.setdefault(canonical_identifier(item.name), []).append(item)
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
        if canonical_identifier(field["name"]) != "FILLER":
            index.setdefault(canonical_identifier(field["effective_name"]), []).append(field)
    local_names = {canonical_identifier(p.name) for p in program.paragraphs} | {
        canonical_identifier(s.name) for s in program.sections
    }

    proc_tokens = [
        t
        for t in tokens
        if procedure_division.start_line <= t.phys_line <= procedure_division.end_line
    ]
    n = len(proc_tokens)
    control_stack: list[dict[str, str]] = []

    for i, tok in enumerate(proc_tokens):
        if tok.kind == "PERIOD":
            control_stack.clear()
            continue
        word = canonical_identifier(tok.value) if tok.kind == "WORD" else ""
        if control_stack and word in _STATEMENT_VERBS:
            top = control_stack[-1]
            if top["type"] == "IF" and top["branch"] == "CONDITION" and word not in {"IF", "ELSE", "END-IF"}:
                top["branch"] = "THEN"
            elif top["type"] == "EVALUATE" and top["branch"] == "CONDITION" and word not in {"WHEN", "END-EVALUATE"}:
                top["branch"] = "BODY"
        if word in {"END-IF", "END-EVALUATE"}:
            expected = "IF" if word == "END-IF" else "EVALUATE"
            if control_stack and control_stack[-1]["type"] == expected:
                control_stack.pop()
        elif word == "ELSE":
            if control_stack and control_stack[-1]["type"] == "IF":
                control_stack[-1]["branch"] = "ELSE"
        elif word == "WHEN":
            if control_stack and control_stack[-1]["type"] == "EVALUATE":
                control_stack[-1]["branch"] = "CONDITION"
        elif word == "IF":
            control_stack.append({"type": "IF", "branch": "CONDITION"})
        elif word == "EVALUATE":
            control_stack.append({"type": "EVALUATE", "branch": "SELECT"})

        if tok.kind != "WORD":
            continue
        key = canonical_identifier(tok.value)
        if key in local_names or key not in index:
            continue

        candidates = index[key]
        target, resolution = _resolve(candidates, proc_tokens, i, n)

        meta: dict = {"program": program.name}
        if control_stack:
            meta["control_context"] = [dict(item) for item in control_stack]
        access = _reference_access(proc_tokens, i)
        edge_type = "USES"
        if access is not None:
            edge_type, operand_role, operation = access
            meta["operand_role"] = operand_role
            meta["operation"] = operation
        if target is not None:
            if isinstance(target, dict):
                meta["copybook_path"] = target["path"]
                meta["target_qualified_name"] = target["qualified_name"]
            elif target.parent:
                meta["parent"] = target.parent

        edge_types = ["READS", "WRITES"] if edge_type == "READS_WRITES" else [edge_type]
        for resolved_type in edge_types:
            edges.append(
                ParsedEdge(
                    type=resolved_type,
                    src_name=_enclosing_paragraph(program, tok.phys_line),
                    dst_name=(target["name"] if isinstance(target, dict) else target.name)
                    if target is not None
                    else tok.value,
                    resolution=resolution,
                    src_start_line=tok.phys_line,
                    src_end_line=tok.phys_line,
                    scope=program.name,
                    # Preserve the same target disambiguation for each direction.
                    meta=dict(meta),
                )
            )

    return edges, errors


def _resolve(
    candidates: list, proc_tokens: list[Token], idx: int, n: int
) -> tuple[object | None, str]:
    if len(candidates) == 1:
        return candidates[0], "resolved"

    qualifier = _qualifier_after(proc_tokens, idx, n)
    if qualifier is not None:
        matches = [
            c
            for c in candidates
            if canonical_identifier(
                (c.get("effective_parent") if isinstance(c, dict) else c.parent) or ""
            )
            == qualifier
        ]
        if len(matches) == 1:
            return matches[0], "resolved"

    return None, "unresolved"


def _qualifier_after(proc_tokens: list[Token], idx: int, n: int) -> str | None:
    nxt = proc_tokens[idx + 1] if idx + 1 < n else None
    if nxt is None or nxt.kind != "WORD" or canonical_identifier(nxt.value) not in _QUALIFIERS:
        return None
    q_tok = proc_tokens[idx + 2] if idx + 2 < n else None
    if q_tok is None or q_tok.kind != "WORD":
        return None
    return canonical_identifier(q_tok.value)


def _enclosing_paragraph(program: CobolProgram, line: int) -> str:
    for p in program.paragraphs:
        if p.start_line <= line <= p.end_line:
            return p.name
    return ""
