"""Shared registry for source structure parsers used by Git ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from cobol.parse import parse_copybook, parse_program
from cobol.prepare import prepare_copybook_index
from core.analysis_fingerprint import grammar_fingerprint as cobol_grammar_fingerprint
from core.model import ParseResult


class StructureParser(Protocol):
    def __call__(
        self, text: str, path: str, *, prepared_source: Any = None, **kwargs: Any
    ) -> ParseResult: ...


PrepareSourceHook = Callable[[str, dict[str, set[str]], dict[str, Any]], Any]
GrammarFingerprint = Callable[[], str]


@dataclass(frozen=True)
class ParserEntry:
    parse: StructureParser
    prepare_source: PrepareSourceHook | None = None
    root_entity_types: tuple[str, ...] = ()
    parser_version: str = "1"
    grammar_fingerprint: GrammarFingerprint | None = None


def _parse_cobol(
    text: str, path: str, *, prepared_source: Any = None, **kwargs: Any
) -> ParseResult:
    """Adapt the COBOL parser's historical ``copybook_index`` argument."""
    return parse_program(text, path, copybook_index=prepared_source, **kwargs)


def _parse_copybook(
    text: str, path: str, *, prepared_source: Any = None, **kwargs: Any
) -> ParseResult:
    return parse_copybook(text, path, copybook_index=prepared_source, **kwargs)


STRUCTURE_PARSERS: dict[str, ParserEntry] = {
    "cobol": ParserEntry(
        parse=_parse_cobol,
        prepare_source=prepare_copybook_index,
        root_entity_types=("program",),
        parser_version="cobol-structure-3",
        grammar_fingerprint=cobol_grammar_fingerprint,
    ),
    "copybook": ParserEntry(
        parse=_parse_copybook,
        prepare_source=prepare_copybook_index,
        root_entity_types=("copybook",),
        parser_version="cobol-structure-3",
        grammar_fingerprint=cobol_grammar_fingerprint,
    ),
}
