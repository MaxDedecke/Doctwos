from types import SimpleNamespace

from core.doc_resolution import resolve_documentation_edges
from resources.asciidoc import parse_asciidoc_file
from resources.asciidoc_prepare import configuration_fingerprint


def prepared(tmp_path, files, attributes=None):
    for path, source in files.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    return {"root": str(tmp_path), "attributes": attributes or {}}


def test_attributes_from_includes_compose_chapters_with_original_source_positions(tmp_path):
    files = {
        "docs/attrs.adoc": ":product: Doctus\n:chapters: chapters\n",
        "docs/chapters/api.adoc": "= {product} API\n\n== Überweisung\nUTF-8 Größe / English text.\n",
    }
    state = prepared(tmp_path, files)
    source = "= Handbuch\ninclude::attrs.adoc[]\ninclude::{chapters}/api.adoc[leveloffset=+1]\n"
    result = parse_asciidoc_file(source, "docs/guide.adoc", prepared_source=state)
    assert not result.diagnostics
    outline = result.entities[0].meta["composition_outline"]
    assert {
        "title": "Doctus API",
        "level": 1,
        "file_path": "docs/chapters/api.adoc",
        "line": 1,
    } in outline
    assert {
        "title": "Überweisung",
        "level": 2,
        "file_path": "docs/chapters/api.adoc",
        "line": 3,
    } in outline
    assert all(
        c.end_line <= 3 and c.meta["physical_file_path"] == "docs/guide.adoc" for c in result.chunks
    )
    assert result.entities[0].meta["attribute_sources"]["product"] == {
        "file_path": "docs/attrs.adoc",
        "line": 1,
    }


def test_conditions_filter_variants_without_changing_line_numbers():
    source = "= Guide\n:lang-de:\nifdef::lang-de[]\n== Deutsch\nendif::[]\nifndef::lang-de[]\n== English\nendif::[]\nifeval::[1 < 2]\n=== Details\nendif::[]\n"
    result = parse_asciidoc_file(source, "guide.adoc")
    sections = {e.name: e.start_line for e in result.entities if e.type == "doc_section"}
    assert sections["Deutsch"] == 4 and sections["Details"] == 10 and "English" not in sections
    assert not result.diagnostics
    assert "English" not in "\n".join(c.content for c in result.chunks)


def test_source_listing_includes_keep_tag_ranges_and_are_not_chapters(tmp_path):
    state = prepared(
        tmp_path,
        {
            "src/Example.java": "// tag::example[]\nclass Example {}\n// end::example[]\n// omitted\n"
        },
    )
    result = parse_asciidoc_file(
        "= Guide\n[source,java]\n----\ninclude::src/Example.java[tag=example]\n----\n",
        "guide.adoc",
        prepared_source=state,
    )
    edge = next(e for e in result.edges if e.type == "INCLUDES")
    assert edge.meta["literal_include"] and edge.meta["selection_ranges"] == [[2, 2]]
    assert len(result.entities[0].meta["composition_outline"]) == 1
    root = SimpleNamespace(
        id=1,
        type="compilation_unit",
        name="Example.java",
        file_path="src/Example.java",
        qualified_name="src/Example.java",
        variant_key="default",
        meta_json={},
    )
    persisted = SimpleNamespace(
        id=2,
        type="INCLUDES",
        dst_name=edge.dst_name,
        variant_key="default",
        resolution="unresolved",
        dst_entity_id=None,
        meta_json=edge.meta,
    )
    assert resolve_documentation_edges([root], [persisted]) == 1 and persisted.dst_entity_id == 1


def test_cycles_missing_files_and_external_urls_are_explicit(tmp_path):
    state = prepared(
        tmp_path, {"a.adoc": "= A\ninclude::b.adoc[]\n", "b.adoc": "= B\ninclude::a.adoc[]\n"}
    )
    result = parse_asciidoc_file(
        "= A\ninclude::b.adoc[]\ninclude::missing.adoc[]\ninclude::https://example.invalid/doc.adoc[]\n",
        "a.adoc",
        prepared_source=state,
    )
    assert any("cyclic" in d.message for d in result.diagnostics)
    assert any("missing.adoc" in d.message for d in result.diagnostics)
    assert any(e.resolution == "external" for e in result.edges if e.type == "INCLUDES")


def test_explicit_attributes_override_document_defaults_and_change_fingerprint(
    tmp_path, monkeypatch
):
    source = ":product: Original\n= {product}\nifdef::de[== Größe]\n"
    result = parse_asciidoc_file(
        source,
        "guide.adoc",
        prepared_source=prepared(tmp_path, {}, {"product": "Configured", "de": ""}),
    )
    assert result.entities[0].meta["doc_title"] == "Configured"
    assert any(e.name == "Größe" for e in result.entities)
    assert not result.diagnostics
    before = configuration_fingerprint()
    monkeypatch.setenv("DOCTUS_ASCIIDOC_ATTRIBUTES", '{"de":""}')
    assert configuration_fingerprint() != before


def test_include_cannot_escape_repository_through_a_symlink(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.adoc"
    outside.write_text("= Outside", encoding="utf-8")
    (root / "escape.adoc").symlink_to(outside)
    result = parse_asciidoc_file(
        "= Guide\ninclude::escape.adoc[]\n", "guide.adoc", prepared_source={"root": str(root)}
    )
    assert result.diagnostics and not any(
        h["title"] == "Outside" for h in result.entities[0].meta["composition_outline"]
    )
