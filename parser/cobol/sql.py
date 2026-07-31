"""
parser/cobol/sql.py
======================
F-027: leichtgewichtiger EXEC-SQL-Klassifikator — Statement-Typ, Tabellen/
Views, Host-Variablen (`:WS-FELD`), Cursor-Namen.

Arbeitet NICHT auf dem Token-Strom von lexer.py, sondern auf dem rohen Text
der `EmbeddedBlock`s, die embedded.mask() (F-034) vor dem Lexen aus der Datei
herausgeschnitten hat — SQL-Syntax (Doppelpunkt, Komma, Klammern) passt nicht
in COBOLs WORD/LITERAL-Token-Grammatik, und genau deshalb existiert embedded.py
als vorgeschalteter Schritt. Kein SQL-Parser, kein Katalogabgleich: reine
Wort-/Regex-Extraktion, "leichtgewichtig" wie im Plan gefordert.

Host-Variablen werden ausschließlich über den führenden Doppelpunkt erkannt
(Standard-Embedded-SQL-Syntax) und dann — wie xref.py es für COBOL-Text tut —
gegen den Datenfeld-Index aufgelöst: genau ein Treffer → resolved, mehrere
oder keiner → unresolved, kein Raten (docs/ENTSCHEIDUNGEN.md E-2-Regel).
Anders als xref.py gibt es innerhalb von SQL-Text kein OF/IN zur
Disambiguierung, also bleibt Mehrdeutigkeit hier immer unresolved.
"""

from __future__ import annotations

import re

from .embedded import EmbeddedBlock
from .model import CobolProgram, DataItem, ParsedEdge, SqlBlock
from .xref import build_index

_STATEMENT_KEYWORDS = {
    "SELECT", "INSERT", "UPDATE", "DELETE", "OPEN", "FETCH", "CLOSE",
    "COMMIT", "ROLLBACK", "INCLUDE", "WHENEVER", "CALL", "EXECUTE", "SET",
}
_CURSOR_STATEMENTS = ("OPEN", "FETCH", "CLOSE")
_TABLE_PRECEDING_KEYWORDS = {"FROM", "JOIN", "INTO"}

_TOKEN_RE = re.compile(r":[A-Za-z][A-Za-z0-9-]*|[A-Za-z][A-Za-z0-9-]*")
_LEADING_EXEC_RE = re.compile(r"\A\s*EXEC\s+\S+\s*", re.IGNORECASE)
_END_EXEC_RE = re.compile(r"END-EXEC", re.IGNORECASE)


def scan(
    program: CobolProgram, blocks: list[EmbeddedBlock], items: list[DataItem] | None = None
) -> tuple[list[SqlBlock], list[ParsedEdge], list[str]]:
    errors: list[str] = []
    sql_blocks: list[SqlBlock] = []
    edges: list[ParsedEdge] = []
    index = build_index(items) if items else {}

    for block in blocks:
        if block.dialect != "SQL":
            continue

        tokens = _TOKEN_RE.findall(_strip_exec_wrapper(block.content))
        statement_type, cursor_name = _classify(tokens)
        tables = _dedupe(_extract_tables(tokens))
        host_variables = _dedupe(tok[1:] for tok in tokens if tok.startswith(":"))

        sql_block = SqlBlock(
            name=f"SQL-BLOCK@{block.start_line}",
            statement_type=statement_type,
            start_line=block.start_line,
            end_line=block.end_line,
            tables=tables,
            host_variables=host_variables,
            cursor_name=cursor_name,
        )
        sql_blocks.append(sql_block)

        for var in host_variables:
            candidates = index.get(var.upper(), [])
            if len(candidates) == 1:
                dst_name, resolution = candidates[0].name, "resolved"
            else:
                dst_name, resolution = var, "unresolved"
            edges.append(
                ParsedEdge(
                    type="USES",
                    src_name=sql_block.name,
                    dst_name=dst_name,
                    resolution=resolution,
                    src_start_line=block.start_line,
                    src_end_line=block.end_line,
                    scope=program.name,
                )
            )

    return sql_blocks, edges, errors


def _strip_exec_wrapper(content: str) -> str:
    body = _LEADING_EXEC_RE.sub("", content, count=1)
    m = _END_EXEC_RE.search(body)
    if m:
        body = body[: m.start()]
    return body


def _classify(tokens: list[str]) -> tuple[str, str | None]:
    if not tokens:
        return "OTHER", None

    first = tokens[0].upper()
    if first == "DECLARE" and len(tokens) >= 3 and tokens[2].upper() == "CURSOR":
        return "DECLARE_CURSOR", tokens[1]
    if first in _STATEMENT_KEYWORDS:
        cursor_name = tokens[1] if first in _CURSOR_STATEMENTS and len(tokens) >= 2 else None
        return first, cursor_name
    return "OTHER", None


def _extract_tables(tokens: list[str]) -> list[str]:
    tables: list[str] = []
    for i, tok in enumerate(tokens):
        upper = tok.upper()
        is_table_slot = upper in _TABLE_PRECEDING_KEYWORDS or (i == 0 and upper == "UPDATE")
        if is_table_slot and i + 1 < len(tokens) and not tokens[i + 1].startswith(":"):
            tables.append(tokens[i + 1])
    return tables


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = v.upper()
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out
