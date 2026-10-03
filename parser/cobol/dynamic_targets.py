"""Belegte Kandidaten für dynamische Aufrufziele (`CALL var`, `EXEC CICS XCTL PROGRAM(var)`).

Ein Aufruf über eine Variable bleibt `dynamic`: das Ziel steht erst zur Laufzeit fest. Der Quelltext
belegt aber oft, welche Programmnamen die Variable annehmen kann, nämlich Literale in
`MOVE 'NAME' TO var` und in der `VALUE`-Klausel des Feldes. Diese Fundstellen werden als
`meta["candidate_targets"]` an die Kante gehängt; die Auflösung ändert sich dadurch nie, und es
entstehen keine zusätzlichen Kanten. Werte, die über andere Felder, Tabellen oder Parameter in die
Variable gelangen, bleiben unsichtbar; die Liste ist deshalb nie als vollständig zu lesen.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .lexer import Token
from .model import ParsedEdge

_PROGRAM_NAME = re.compile(r"[A-Za-z0-9#@$][A-Za-z0-9#@$-]{0,29}")
_MAX_CANDIDATES = 20


def _literal(value: str) -> str | None:
    text = value.strip()
    if text[:1] in "NXGZ" and len(text) > 1 and text[1] in "'\"":
        text = text[1:]
    if len(text) < 2 or text[0] not in "'\"" or text[-1] != text[0]:
        return None
    inner = text[1:-1].strip()
    return inner if _PROGRAM_NAME.fullmatch(inner) else None


def literal_assignments(tokens: list[Token]) -> dict[str, list[tuple[str, int, str]]]:
    """Feldname (groß) -> [(Literal, Zeile, `move`|`value`)] in Quelltextreihenfolge."""
    found: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    current_item: str | None = None
    count = len(tokens)
    for index, token in enumerate(tokens):
        if token.kind == "NUMBER" and token.value.isdigit() and index + 1 < count:
            level = int(token.value)
            following = tokens[index + 1]
            if (1 <= level <= 49 or level == 77) and following.kind == "WORD":
                current_item = None if following.value.upper() == "FILLER" else following.value.upper()
            continue
        if token.kind != "WORD":
            continue
        word = token.value.upper()
        if word == "VALUE" and current_item and index + 1 < count:
            nxt = index + 1
            if tokens[nxt].kind == "WORD" and tokens[nxt].value.upper() in {"IS", "ARE"} and nxt + 1 < count:
                nxt += 1
            literal = _literal(tokens[nxt].value) if tokens[nxt].kind == "LITERAL" else None
            if literal:
                found[current_item].append((literal, tokens[nxt].phys_line, "value"))
        elif word == "MOVE" and index + 3 < count and tokens[index + 1].kind == "LITERAL":
            literal = _literal(tokens[index + 1].value)
            if literal and tokens[index + 2].kind == "WORD" and tokens[index + 2].value.upper() == "TO":
                receiver = tokens[index + 3]
                if receiver.kind == "WORD":
                    found[receiver.value.upper()].append((literal, tokens[index + 1].phys_line, "move"))
    return found


def annotate(edges: list[ParsedEdge], tokens: list[Token], first_line: int, last_line: int) -> None:
    """Hängt belegte Kandidaten an dynamische `CALL`-Kanten desselben Programms."""
    dynamic = [e for e in edges if e.type == "CALL" and e.resolution == "dynamic"]
    if not dynamic:
        return
    scope = [t for t in tokens if first_line <= t.phys_line <= last_line]
    table = literal_assignments(scope)
    for edge in dynamic:
        entries = table.get(edge.dst_name.upper().split("(", 1)[0].strip(), [])
        if not entries:
            continue
        merged: dict[str, dict] = {}
        for literal, line, source in entries:
            item = merged.setdefault(literal.upper(), {"name": literal, "line": line, "source": source, "count": 0})
            item["count"] += 1
        edge.meta["candidate_targets"] = list(merged.values())[:_MAX_CANDIDATES]
        edge.meta["candidate_basis"] = "literal_assignments_in_program"
