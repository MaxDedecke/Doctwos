"""
parser/cobol
============
COBOL-AST-Parser (F-020…F-034, Plan §6). Deterministisch, kein LLM, kein
Abbruch bei Fehlern — siehe CLAUDE.md „Zeilennummern sind heilig".

Aufbaustand: Fundament (source_format, embedded, lexer), Struktur (divisions,
procedure), Datenfelder (data_division, xref), Copybooks (copybook) und
EXEC-SQL-Klassifikation (sql) — siehe docs/UMSETZUNGSSTAND.md für den
aktuellen Stand von AP-2.
"""
