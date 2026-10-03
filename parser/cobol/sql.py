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

O-138: `own_range` grenzt `blocks` bei mehreren/verschachtelten Programmen
auf die EXEC-SQL-Vorkommen DIESES Programms ein, und `meta["program"]` macht
die Programmzugehörigkeit für `structure_persist.py` sichtbar - siehe
procedure.py-Docstring für die ausführliche Begründung.
"""

from __future__ import annotations

import re

from .embedded import EmbeddedBlock
from .model import CobolProgram, DataItem, ParsedEdge, SqlBlock
from .xref import build_index

_STATEMENT_KEYWORDS = {
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "OPEN",
    "FETCH",
    "CLOSE",
    "COMMIT",
    "ROLLBACK",
    "INCLUDE",
    "WHENEVER",
    "CALL",
    "EXECUTE",
    "SET",
    # DB2-Anweisungen, die in Programmen vorkommen, aber nicht „OTHER“ heißen dürfen:
    "MERGE",
    "PREPARE",
    "DESCRIBE",
    "LOCK",
    "SAVEPOINT",
    "RELEASE",
    "CONNECT",
    "TRUNCATE",
    "VALUES",
}
_CURSOR_STATEMENTS = ("OPEN", "FETCH", "CLOSE")
_SELECT_CLAUSE_KEYWORDS = {
    "FROM",
    "WHERE",
    "GROUP",
    "HAVING",
    "ORDER",
    "FOR",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "FETCH",
    "OPTIMIZE",
    "WITH",
}

_TOKEN_RE = re.compile(
    r":[A-Za-z][A-Za-z0-9_-]*|[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z][A-Za-z0-9_-]*)*"
)
_LEADING_EXEC_RE = re.compile(r"\A\s*EXEC\s+\S+\s*", re.IGNORECASE)
_END_EXEC_RE = re.compile(r"END-EXEC", re.IGNORECASE)


def scan(
    program: CobolProgram,
    blocks: list[EmbeddedBlock],
    items: list[DataItem] | None = None,
    own_range: tuple[int, int] | None = None,
) -> tuple[list[SqlBlock], list[ParsedEdge], list[str]]:
    errors: list[str] = []
    sql_blocks: list[SqlBlock] = []
    edges: list[ParsedEdge] = []
    index = build_index(items) if items else {}

    # O-138: `blocks` stammt aus embedded.mask() über die GESAMTE Datei - bei
    # mehreren/verschachtelten Programmen setzt parse.py `own_range` (aus den
    # AST-Divisionsgrenzen dieses Programms, cobol/model.py::program_own_range()),
    # sonst würde ein SQL-Block aus Programm A auch beim Scan von Programm B
    # noch einmal als dessen SqlBlock/USES-Kante auftauchen. Default None
    # (Einzelprogramm-Normalfall) bleibt unfiltriert - Vertrauen auf die
    # Divisions-AST-Grenzen wäre riskant, sobald eine Division nicht sauber
    # geparst wurde (z.B. eine fehlende "DATA DIVISION."-Kopfzeile).
    for block in blocks:
        if block.dialect != "SQL":
            continue
        if own_range is not None and not (own_range[0] <= block.start_line <= own_range[1]):
            continue

        cleaned_text = _clean_sql_text(block.content)
        tokens = _TOKEN_RE.findall(cleaned_text)
        statement_type, cursor_name = _classify(tokens)
        include_name = tokens[1] if statement_type == "INCLUDE" and len(tokens) >= 2 else None
        table_entries = _extract_tables_with_access(tokens, statement_type)
        tables = _dedupe([t[0] for t in table_entries])
        host_variables = _dedupe(tok[1:] for tok in tokens if tok.startswith(":"))

        sql_block = SqlBlock(
            name=f"SQL-BLOCK@{block.start_line}",
            statement_type=statement_type,
            start_line=block.start_line,
            end_line=block.end_line,
            tables=tables,
            host_variables=host_variables,
            cursor_name=cursor_name,
            include_name=include_name,
        )
        sql_blocks.append(sql_block)

        for var in host_variables:
            candidates = index.get(var.upper(), [])
            if len(candidates) == 1:
                dst_name, resolution = candidates[0].name, "resolved"
            else:
                dst_name, resolution = var, "unresolved"
            access = _host_variable_access(tokens, statement_type, var)
            edges.append(
                ParsedEdge(
                    type=access,
                    src_name=sql_block.name,
                    dst_name=dst_name,
                    resolution=resolution,
                    src_start_line=block.start_line,
                    src_end_line=block.end_line,
                    scope=program.name,
                    meta={"program": program.name, "access": access},
                )
            )

        seen_table_edges: set[tuple[str, str]] = set()
        for table, table_access in table_entries:
            key = (table.upper(), table_access)
            if key in seen_table_edges:
                continue
            seen_table_edges.add(key)
            edges.append(
                ParsedEdge(
                    type=table_access,
                    src_name=sql_block.name,
                    dst_name=table,
                    resolution="resolved",
                    src_start_line=block.start_line,
                    src_end_line=block.end_line,
                    scope=program.name,
                    meta={
                        "program": program.name,
                        "access": table_access,
                        "target_qualified_name": (
                            f"{program.name}.SQL-TABLE@{table.upper()}"
                        ),
                    },
                )
            )

    return sql_blocks, edges, errors


def _clean_sql_text(content: str) -> str:
    body = _LEADING_EXEC_RE.sub("", content, count=1)
    m = _END_EXEC_RE.search(body)
    if m:
        body = body[: m.start()]
    # Remove single-line comments -- ...
    body = re.sub(r"--[^\n]*", " ", body)
    # Remove multi-line comments /* ... */
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.DOTALL)
    # Replace single-quoted string literals with empty string ''
    body = re.sub(r"'([^']|'')*'", "''", body)
    return body


def _classify(tokens: list[str]) -> tuple[str, str | None]:
    if not tokens:
        return "OTHER", None

    first = tokens[0].upper()
    if first == "DECLARE" and len(tokens) >= 3 and tokens[2].upper() == "CURSOR":
        return "DECLARE_CURSOR", tokens[1]
    if first == "EXECUTE" and len(tokens) >= 2 and tokens[1].upper() == "IMMEDIATE":
        return "EXECUTE_IMMEDIATE", None
    if first in _STATEMENT_KEYWORDS:
        cursor_name = tokens[1] if first in _CURSOR_STATEMENTS and len(tokens) >= 2 else None
        return first, cursor_name
    return "OTHER", None


def _extract_tables_with_access(tokens: list[str], statement_type: str) -> list[tuple[str, str]]:
    table_entries: list[tuple[str, str]] = []
    is_delete_target = statement_type == "DELETE"

    for i, tok in enumerate(tokens):
        upper = tok.upper()
        if i == 0 and upper == "UPDATE" and i + 1 < len(tokens) and not tokens[i + 1].startswith(":"):
            table_entries.append((tokens[i + 1], "WRITES"))
        elif (
            upper == "INTO"
            and statement_type == "INSERT"
            and i + 1 < len(tokens)
            and not tokens[i + 1].startswith(":")
        ):
            table_entries.append((tokens[i + 1], "WRITES"))
        elif upper == "FROM":
            if is_delete_target and i + 1 < len(tokens) and not tokens[i + 1].startswith(":"):
                table_entries.append((tokens[i + 1], "WRITES"))
                is_delete_target = False
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith(":"):
                table_entries.append((tokens[i + 1], "READS"))
        elif upper == "JOIN" and i + 1 < len(tokens) and not tokens[i + 1].startswith(":"):
            table_entries.append((tokens[i + 1], "READS"))
        elif (
            statement_type == "MERGE"
            and upper in {"INTO", "USING"}
            and i + 1 < len(tokens)
            and not tokens[i + 1].startswith(":")
            and tokens[i + 1].upper() not in {"(", "SELECT", "TABLE"}
        ):
            # MERGE INTO <Ziel> USING <Quelle>: das Ziel wird geschrieben, die Quelle gelesen.
            table_entries.append((tokens[i + 1], "WRITES" if upper == "INTO" else "READS"))
        elif (
            statement_type == "TRUNCATE"
            and upper == "TABLE"
            and i + 1 < len(tokens)
            and not tokens[i + 1].startswith(":")
        ):
            table_entries.append((tokens[i + 1], "WRITES"))

    return table_entries


def _host_variable_access(tokens: list[str], statement_type: str, variable: str) -> str:
    """Classify a host variable without guessing beyond SQL's clear clauses."""
    positions = [
        i for i, token in enumerate(tokens) if token.upper() == f":{variable.upper()}"
    ]
    position = positions[0] if positions else -1
    if position == -1:
        return "USES"

    if statement_type == "FETCH":
        into_position = next(
            (i for i, token in enumerate(tokens) if token.upper() == "INTO"), None
        )
        if into_position is not None and position > into_position:
            return "WRITES"
        return "READS"

    if statement_type == "SELECT":
        into_position = next(
            (i for i, token in enumerate(tokens) if token.upper() == "INTO"), None
        )
        if into_position is not None and position > into_position:
            next_clause = next(
                (
                    i
                    for i in range(into_position + 1, len(tokens))
                    if tokens[i].upper() in _SELECT_CLAUSE_KEYWORDS
                ),
                None,
            )
            if next_clause is None or position < next_clause:
                return "WRITES"
        return "READS"

    if statement_type in {"INSERT", "UPDATE", "DELETE", "DECLARE_CURSOR", "OPEN"}:
        return "READS"
    return "USES"


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        key = v.upper()
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out
