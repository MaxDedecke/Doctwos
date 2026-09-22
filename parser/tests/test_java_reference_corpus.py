"""Offline acceptance contract for the versioned Java reference corpus.

The corpus is intentionally synthetic.  It protects the parser's known Java
surface without claiming that it replaces the customer-specific O-240 sample.
"""

from __future__ import annotations

from pathlib import Path

from java.parse import parse_java_file


FIXTURE_ROOT = Path(__file__).parent / "java_corpus" / "fixtures"


def _parse(relative_path: str):
    fixture = FIXTURE_ROOT / relative_path
    return parse_java_file(fixture.read_text(encoding="utf-8"), relative_path)


def test_java_reference_corpus_covers_declared_language_surfaces() -> None:
    legacy = _parse("java8_overloads.java")
    modern = _parse("java21_patterns.java")
    lombok = _parse("lombok_accessors.java")
    billing = _parse("billing/src/main/java/corpus/billing/BillingService.java")

    legacy_names = {entity.qualified_name for entity in legacy.entities}
    assert legacy.diagnostics == []
    assert {
        "corpus.legacy.Catalog#<init>(List<T>)",
        "corpus.legacy.Catalog#find(int)",
        "corpus.legacy.Catalog#find(String)",
        "corpus.legacy.Catalog.Entry",
    } <= legacy_names

    modern_names = {entity.qualified_name for entity in modern.entities}
    assert modern.diagnostics == []
    assert {
        "corpus.modern.Shape",
        "corpus.modern.Circle",
        "corpus.modern.Circle#component:radius",
        "corpus.modern.Rectangle#component:width",
        "corpus.modern.Area#calculate(Shape)",
    } <= modern_names

    generated = next(
        entity
        for entity in lombok.entities
        if entity.qualified_name == "corpus.lombok.Customer#getName()"
    )
    assert lombok.diagnostics == []
    assert generated.meta["synthetic"] is True
    assert generated.meta["generated_by"] == "lombok"
    assert generated.meta["source_field"] == "corpus.lombok.Customer#name"
    assert (generated.start_line, generated.end_line) == (9, 9)

    assert billing.diagnostics == []
    assert all(entity.meta["module"] == "billing" for entity in billing.entities)
    assert all(entity.meta["source_set"] == "main" for entity in billing.entities)
    assert all(entity.meta["source_kind"] == "source" for entity in billing.entities)


def test_java_reference_corpus_preserves_error_positions_and_fallback() -> None:
    broken = _parse("broken.java")

    diagnostic = next(item for item in broken.diagnostics if item.code == "JAVA_PARSER_ERROR")
    assert (diagnostic.line, diagnostic.column) == (5, 18)
    assert broken.chunks
    # Recovery keeps the valid surrounding declaration structure. A complete
    # text fallback is reserved for files with no extractable declaration.
    assert any(
        entity.qualified_name == "corpus.damaged.Broken#recover()"
        for entity in broken.entities
    )
    assert not any(chunk.meta.get("fallback") for chunk in broken.chunks)
