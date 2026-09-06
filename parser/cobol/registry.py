"""
parser/cobol/registry.py
=========================
O-077: Dispatch-Registry, über die GitConnector._embed_document eine Sprache
(`doc["extra_meta"]["language"]`) auf ihren Struktur-Parser abbildet, statt der
zuvor hartkodierten `if lang in {"cobol", "copybook"}`-Weiche in
parser/connectors/git.py.

COBOL/Copybook bleiben der einzige echte Eintrag -- das ist bewusst so, siehe
docs/OFFENE_ENTWICKLUNGSPUNKTE.md O-077. Genau so eine pluggbare Mehrsprachen-
Schicht (`parser/languages/`, `PARSER_REGISTRY`) gab es schon einmal und wurde
laut docs/TECH_DEBT_CLEANUP_PLAN.md §1a wieder entfernt, weil sie nie
produktiv befüllt war (CLAUDE.md Prinzip 3, "keine Importierung auf Vorrat").
Diese Registry hier ist deshalb bewusst klein gehalten: kein eigenes Paket,
keine Interfaces über das hinaus, was der eine reale Konsument (COBOL)
braucht. Der Dispatch-Mechanismus selbst ist in
parser/tests/test_git_connector.py mit einem Fake-Eintrag abgesichert.
"""

from typing import Protocol

from cobol.copybook import CopybookIndex
from cobol.parse import parse_copybook, parse_program
from core.model import ParseResult


class StructureParser(Protocol):
    """Signatur, die jeder Registry-Eintrag erfüllen muss -- exakt das, was
    parse_program()/parse_copybook() heute schon liefern (chunk_size bei
    parse_copybook hat einen Default, bleibt hier also außen vor)."""

    def __call__(self, text: str, path: str, copybook_index: CopybookIndex | None) -> ParseResult: ...


# lang (Wert aus classify_extension()/spaces["cobol_extensions"]) -> Struktur-Parser.
STRUCTURE_PARSERS: dict[str, StructureParser] = {
    "cobol": parse_program,
    "copybook": parse_copybook,
}
