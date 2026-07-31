"""
parser/cobol
============
COBOL-AST-Parser (F-020…F-034, Plan §6). Deterministisch, kein LLM, kein
Abbruch bei Fehlern — siehe CLAUDE.md „Zeilennummern sind heilig".

Aufbaustand: Fundament (source_format, embedded, lexer), Struktur (divisions,
procedure), Datenfelder (data_division, xref), Copybooks (copybook),
EXEC-SQL-Klassifikation (sql), Chunking (chunking, AP-4 vorgezogen) und die
In-Memory-Orchestrierung `parse.parse_program()` — siehe
docs/UMSETZUNGSSTAND.md für den aktuellen Stand von AP-2.
"""
