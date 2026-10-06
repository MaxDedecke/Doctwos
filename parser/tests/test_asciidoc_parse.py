from types import SimpleNamespace

from core.doc_resolution import resolve_documentation_edges
from resources.asciidoc import classify_mention, parse_asciidoc_file

SOURCE = """= Reference Guide
:toc:

[[concepts]]
== Concepts

Users are managed through `UserTO` and `org.apache.syncope.common.lib.to.GroupTO`.

=== Tasks

A `Realm` has the key `connector.bundles.dir` configured in `core/src/main/resources/core.properties`.

----
== not a heading
`IgnoredInsideListing`
----

include::policies.adoc[]

== Workflow

See `AnyTO`.
"""


def test_sections_nest_and_end_before_the_next_heading_of_the_same_or_a_higher_level():
    result = parse_asciidoc_file(SOURCE, "docs/guide.adoc")
    by_name = {e.name: e for e in result.entities}
    assert by_name["guide.adoc"].type == "asciidoc_document" and by_name["guide.adoc"].meta["doc_title"] == "Reference Guide"
    concepts, tasks, workflow = by_name["Concepts"], by_name["Tasks"], by_name["Workflow"]
    assert concepts.meta["anchor"] == "concepts" and concepts.qualified_name == "docs/guide.adoc::section:concepts"
    assert tasks.parent_qualified_name == concepts.qualified_name
    assert concepts.start_line < tasks.start_line <= concepts.end_line < workflow.start_line
    assert workflow.parent_qualified_name == by_name["Reference Guide"].qualified_name
    assert "not a heading" not in by_name


def test_mentions_become_documents_edges_from_the_enclosing_section_and_listings_are_ignored():
    result = parse_asciidoc_file(SOURCE, "docs/guide.adoc")
    documents = {(e.src_name.split("::section:")[1], e.dst_name, e.meta["mention_kind"])
                 for e in result.edges if e.type == "DOCUMENTS"}
    assert ("concepts", "UserTO", "type_name") in documents
    assert ("concepts", "org.apache.syncope.common.lib.to.GroupTO", "qualified_name") in documents
    assert ("tasks", "Realm", "type_name") in documents
    assert ("tasks", "connector.bundles.dir", "property_key") in documents
    assert ("tasks", "core/src/main/resources/core.properties", "file_path") in documents
    assert ("workflow", "AnyTO", "type_name") in documents
    assert not any(dst == "IgnoredInsideListing" for _, dst, _ in documents)


def test_include_directives_become_resolvable_edges_relative_to_the_file():
    result = parse_asciidoc_file(SOURCE, "docs/guide.adoc")
    include = next(e for e in result.edges if e.type == "INCLUDES")
    assert include.meta["target_file_path"] == "docs/policies.adoc"
    assert include.src_name.endswith("::section:tasks")


def test_classification_only_accepts_object_like_names():
    assert classify_mention("UserTO") == ("type_name", "UserTO")
    assert classify_mention("@Transactional()") == ("type_name", "Transactional")
    assert classify_mention("a.b.Thing") == ("qualified_name", "a.b.Thing")
    assert classify_mention("SSO") is None
    assert classify_mention("some text here") is None
    assert classify_mention("create()") is None


def _entity(i, type_, name, file_path="X.java", qname=None, meta=None):
    return SimpleNamespace(id=i, type=type_, name=name, file_path=file_path, qualified_name=qname or name,
                           variant_key="default", meta_json=meta)


def _edge(i, kind, dst, edge_type="DOCUMENTS", **meta):
    return SimpleNamespace(id=i, type=edge_type, dst_name=dst, variant_key="default", resolution="unresolved",
                           dst_entity_id=None, meta_json={"language": "asciidoc", "mention_kind": kind, **meta})


def test_resolution_links_only_unique_targets_and_marks_ambiguous_ones():
    entities = [
        _entity(1, "class", "UserTO", qname="org.x.UserTO"),
        _entity(2, "class", "Realm", qname="org.a.Realm"),
        _entity(3, "class", "Realm", qname="org.b.Realm"),
        _entity(4, "property", "k", meta={"property_key": "connector.bundles.dir"}),
        _entity(5, "properties_file", "core.properties", file_path="core/src/main/resources/core.properties"),
        _entity(6, "asciidoc_document", "policies.adoc", file_path="docs/policies.adoc"),
    ]
    edges = [
        _edge(10, "type_name", "UserTO"), _edge(11, "type_name", "Realm"), _edge(12, "qualified_name", "org.b.Realm"),
        _edge(13, "property_key", "connector.bundles.dir"), _edge(14, "file_path", "core/src/main/resources/core.properties"),
        _edge(15, "type_name", "Missing"), _edge(16, None, "x", "INCLUDES", target_file_path="docs/policies.adoc"),
    ]
    resolved = resolve_documentation_edges(entities, edges)
    by_id = {e.id: e for e in edges}
    assert resolved == 5
    assert by_id[10].dst_entity_id == 1 and by_id[10].resolution == "resolved"
    assert by_id[11].dst_entity_id is None and by_id[11].meta_json["ambiguous_candidates"] == 2
    assert by_id[12].dst_entity_id == 3
    assert by_id[13].dst_entity_id == 4 and by_id[14].dst_entity_id == 5 and by_id[16].dst_entity_id == 6
    assert by_id[15].dst_entity_id is None and by_id[15].resolution == "unresolved"
    # Ein später verschwundenes Ziel macht eine zuvor aufgelöste Kante wieder unaufgelöst.
    resolve_documentation_edges([], [by_id[10]])
    assert by_id[10].resolution == "unresolved" and by_id[10].dst_entity_id is None
