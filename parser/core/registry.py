"""Shared registry for source structure parsers used by Git ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from cobol.parse import parse_copybook, parse_program
from cobol.prepare import prepare_copybook_index
from core.analysis_fingerprint import grammar_fingerprint as cobol_grammar_fingerprint
from core.model import ParseResult
from java.fingerprint import grammar_fingerprint as java_grammar_fingerprint
from java.parse import parse_java_file
from maven.parse import parse_maven_pom
from markup.parse import parse_xml_document
from markup.jsp_html import parse_jsp_or_html
from shell.parse import parse_shell_file
from xslt.parse import parse_xslt_file


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


def _parse_java(text: str, path: str, *, prepared_source: Any = None, **kwargs: Any) -> ParseResult:
    """Adapt the generic registry contract to Java's source-only parser."""
    return parse_java_file(
        text,
        path,
        max_diagnostics=kwargs.get("max_diagnostics", 50),
    )


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
    "java": ParserEntry(
        parse=_parse_java,
        root_entity_types=("compilation_unit",),
        parser_version="java-structure-1",
        grammar_fingerprint=java_grammar_fingerprint,
    ),
    "maven": ParserEntry(
        parse=parse_maven_pom,
        root_entity_types=("maven_project",),
        parser_version="maven-structure-1",
    ),
    "xslt": ParserEntry(
        parse=parse_xslt_file,
        root_entity_types=("xslt_stylesheet",),
        parser_version="xslt-structure-1",
    ),
    # XML gets a deliberately small document-root parser so XSLT's static
    # READS_XML relationships can point at a navigable entity.  Vocabulary-
    # specific semantics remain the responsibility of future parsers.
    "xml": ParserEntry(
        parse=parse_xml_document,
        root_entity_types=("xml_document",),
        parser_version="xml-root-1",
    ),
    "html": ParserEntry(parse=parse_jsp_or_html, root_entity_types=("html_document",), parser_version="html-structure-1"),
    "jsp": ParserEntry(parse=parse_jsp_or_html, root_entity_types=("jsp_page",), parser_version="jsp-structure-1"),
    "shell": ParserEntry(parse=parse_shell_file, root_entity_types=("shell_script",), parser_version="shell-structure-1"),
}
