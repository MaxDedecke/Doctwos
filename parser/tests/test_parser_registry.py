from core import registry
from core.analysis_fingerprint import analysis_fingerprint
from cobol.profile import BuildProfile


def test_cobol_registry_adapts_generic_prepared_source_to_legacy_parser_argument(monkeypatch):
    calls = []

    def fake_parse_program(text, path, *, copybook_index=None, profile=None):
        calls.append((text, path, copybook_index, profile))
        return object()

    monkeypatch.setattr(registry, "parse_program", fake_parse_program)
    prepared_source = {"COPYBOOK": ["copybook.cpy"]}
    profile = BuildProfile()

    result = registry.STRUCTURE_PARSERS["cobol"].parse(
        "source", "program.cbl", prepared_source=prepared_source, profile=profile
    )

    assert result is not None
    assert calls == [("source", "program.cbl", prepared_source, profile)]


def test_shared_registry_declares_roots_and_parser_analysis_inputs():
    cobol_entry = registry.STRUCTURE_PARSERS["cobol"]
    copybook_entry = registry.STRUCTURE_PARSERS["copybook"]

    assert cobol_entry.root_entity_types == ("program",)
    assert copybook_entry.root_entity_types == ("copybook",)
    assert cobol_entry.parser_version == "cobol-structure-3"
    assert cobol_entry.grammar_fingerprint is not None
    assert len(cobol_entry.grammar_fingerprint()) == 64

    java_entry = registry.STRUCTURE_PARSERS["java"]
    assert java_entry.root_entity_types == ("compilation_unit",)
    assert java_entry.parser_version == "java-structure-2"
    assert len(java_entry.grammar_fingerprint()) == 64


def test_java_registry_entry_produces_entities_and_symbol_chunks():
    result = registry.STRUCTURE_PARSERS["java"].parse(
        "package sample; class App { void run() {} }", "src/App.java"
    )

    assert result.entities[0].type == "compilation_unit"
    assert result.entities[0].meta["is_file_root"] is True
    assert any(entity.qualified_name == "sample.App#run()" for entity in result.entities)
    assert any(chunk.meta.get("symbol_type") == "method" for chunk in result.chunks)


def test_markup_registry_entries_produce_navigable_roots():
    xslt = registry.STRUCTURE_PARSERS["xslt"].parse(
        '<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"/>',
        "styles/main.xsl",
    )
    xml = registry.STRUCTURE_PARSERS["xml"].parse("<root/>", "input.xml")

    assert registry.STRUCTURE_PARSERS["xslt"].root_entity_types == ("xslt_stylesheet",)
    assert registry.STRUCTURE_PARSERS["xml"].root_entity_types == ("xml_document",)
    assert xslt.entities[0].type == "xslt_stylesheet"
    assert xml.entities[0].type == "xml_document"
    assert registry.STRUCTURE_PARSERS["jsp"].parse("${order.id}", "view.jsp").entities[0].type == "jsp_page"


def test_registry_inputs_preserve_existing_cobol_analysis_fingerprint():
    entry = registry.STRUCTURE_PARSERS["cobol"]
    shared_fingerprint = analysis_fingerprint(
        source_revision="blob-sha",
        profile=BuildProfile(),
        parser_version=entry.parser_version,
        grammar_version=entry.grammar_fingerprint(),
    )
    legacy_fingerprint = analysis_fingerprint(
        source_revision="blob-sha",
        profile=BuildProfile(),
        parser_version="cobol-structure-3",
    )

    assert shared_fingerprint == legacy_fingerprint
