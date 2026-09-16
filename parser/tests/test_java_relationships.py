from __future__ import annotations

from cobol_persist import _build_edge
from java.parse import parse_java_file
from java.resolution import resolve_global_edges
from models.database import CodeEdge, CodeEntity
from tasks.edge_resolver import _java_parse_results


def test_java_relationships_capture_declarations_calls_and_field_accesses() -> None:
    result = parse_java_file(
        """package demo;
import java.util.List;
import static java.util.Objects.requireNonNull;

class Child extends Parent implements Runnable {
    List<String> names;

    Child() {
        new Helper();
    }

    public void run() {
        count = requireNonNull(names).size();
        helper();
        Child.<String>genericCall(names);
        this.count++;
        other.value = count;
    }

    int count;
}
""",
        "src/demo/Child.java",
    )

    imports = [edge for edge in result.edges if edge.type == "IMPORTS"]
    assert [(edge.dst_name, edge.meta["static"]) for edge in imports] == [
        ("java.util.List", False),
        ("java.util.Objects.requireNonNull", True),
    ]

    inheritance = [
        (edge.type, edge.dst_name)
        for edge in result.edges
        if edge.type in {"EXTENDS", "IMPLEMENTS"}
    ]
    assert inheritance == [("EXTENDS", "Parent"), ("IMPLEMENTS", "Runnable")]

    method_qname = "demo.Child#run()"
    method_edges = [edge for edge in result.edges if edge.src_name == method_qname]
    assert any(edge.type == "USES_TYPE" and edge.dst_name == "String" for edge in result.edges)
    assert any(
        edge.type == "INSTANTIATES"
        and edge.dst_name == "Helper"
        and edge.meta["invocation_kind"] == "constructor"
        for edge in result.edges
    )
    calls = [edge for edge in method_edges if edge.type == "CALLS"]
    assert [(edge.dst_name, edge.meta["argument_count"]) for edge in calls] == [
        ("requireNonNull", 1),
        ("requireNonNull(names).size", 0),
        ("helper", 0),
        ("Child.genericCall", 1),
    ]

    writes = [edge for edge in method_edges if edge.type == "WRITES"]
    assert [edge.dst_name for edge in writes] == ["count", "count", "other.value"]
    reads = [edge for edge in method_edges if edge.type == "READS"]
    assert [edge.dst_name for edge in reads] == ["names", "names", "count", "count"]
    assert all(edge.resolution in {"resolved", "unresolved"} for edge in result.edges)
    assert all(
        edge.resolution == "resolved"
        for edge in writes + reads
        if edge.dst_name in {"names", "count"}
    )
    assert (
        next(edge for edge in writes if edge.dst_name == "other.value").resolution == "unresolved"
    )
    assert any(edge.resolution == "unresolved" for edge in result.edges)
    assert all(edge.src_start_line == edge.src_end_line for edge in result.edges)


def test_java_relationships_keep_wildcard_import_and_nested_type_usage() -> None:
    result = parse_java_file(
        """package demo;
import java.util.*;
class Outer {
    static class Inner {}
    Map<String, Inner> values;
}
""",
        "Outer.java",
    )

    wildcard = next(edge for edge in result.edges if edge.type == "IMPORTS")
    assert wildcard.dst_name == "java.util.*"
    assert wildcard.meta["wildcard"] is True
    usages = [edge.dst_name for edge in result.edges if edge.type == "USES_TYPE"]
    assert usages == ["Map<String,Inner>", "String", "Inner"]


def test_java_local_resolution_handles_overloads_and_nested_constructors() -> None:
    result = parse_java_file(
        """package demo;
class Local {
    int count;
    void target() {}
    void overloaded(int value) {}
    void overloaded(String value) {}

    void caller() {
        target();
        overloaded(1);
        overloaded("text");
        overloaded(null);
        new Helper(1);
        count = 1;
    }

    static class Helper {
        Helper(int value) {}
    }
}
""",
        "Local.java",
    )

    caller_edges = [edge for edge in result.edges if edge.src_name == "demo.Local#caller()"]
    calls = [edge for edge in caller_edges if edge.type == "CALLS"]
    targets = {edge.dst_name: edge for edge in calls}
    assert targets["target"].resolution == "resolved"
    assert targets["target"].meta["target_qualified_name"] == "demo.Local#target()"
    assert targets["overloaded"].resolution == "unresolved"
    assert targets["overloaded"].meta["resolution_reason"] == "ambiguous_overload"
    assert [edge.resolution for edge in calls] == ["resolved", "resolved", "resolved", "unresolved"]

    overload_targets = [
        edge.meta.get("target_qualified_name")
        for edge in calls
        if edge.dst_name == "overloaded" and edge.resolution == "resolved"
    ]
    assert overload_targets == ["demo.Local#overloaded(int)", "demo.Local#overloaded(String)"]

    created = next(edge for edge in result.edges if edge.type == "INSTANTIATES")
    assert created.resolution == "resolved"
    assert created.meta["target_qualified_name"] == "demo.Local.Helper#<init>(int)"

    write = next(edge for edge in caller_edges if edge.type == "WRITES")
    assert write.resolution == "resolved"
    assert write.meta["target_qualified_name"] == "demo.Local#count"


def test_java_global_resolution_applies_imports_and_static_imports() -> None:
    service = parse_java_file(
        """package api;
public class Service {
    public Service() {}
    public void run(int value) {}
    public static int parse(int value) { return value; }
}
""",
        "api/Service.java",
    )
    client = parse_java_file(
        """package app;
import api.Service;
import static api.Service.parse;
class Client {
    void call() {
        new Service().run(1);
        parse(1);
    }
}
""",
        "app/Client.java",
    )

    assert resolve_global_edges([service, client]) == 3
    edges = [edge for edge in client.edges if edge.src_name == "app.Client#call()"]
    created = next(edge for edge in edges if edge.type == "INSTANTIATES")
    run = next(edge for edge in edges if edge.type == "CALLS" and edge.meta["method_name"] == "run")
    parsed = next(
        edge for edge in edges if edge.type == "CALLS" and edge.meta["method_name"] == "parse"
    )
    assert created.meta["target_qualified_name"] == "api.Service#<init>()"
    assert run.meta["target_qualified_name"] == "api.Service#run(int)"
    assert parsed.meta["target_qualified_name"] == "api.Service#parse(int)"
    assert all(edge.meta["resolution_scope"] == "global" for edge in (created, run, parsed))


def test_java_global_resolution_does_not_guess_missing_or_ambiguous_imports() -> None:
    first = parse_java_file("package one; public class Shared {}\n", "one/Shared.java")
    second = parse_java_file("package two; public class Shared {}\n", "two/Shared.java")
    client = parse_java_file(
        """package app;
import one.*;
import two.*;
class Client {
    Shared value;
    one.Shared explicit;
    void missing() { new Unimported(); }
}
""",
        "app/Client.java",
    )

    assert resolve_global_edges([first, second, client]) == 1
    usages = [edge for edge in client.edges if edge.type == "USES_TYPE"]
    ambiguous = next(edge for edge in usages if edge.dst_name == "Shared")
    explicit = next(edge for edge in usages if edge.dst_name == "one.Shared")
    assert ambiguous.resolution == "unresolved"
    assert ambiguous.meta["resolution_reason"] == "ambiguous_type"
    assert explicit.resolution == "resolved"
    assert explicit.meta["target_qualified_name"] == "one.Shared"
    created = next(edge for edge in client.edges if edge.type == "INSTANTIATES")
    assert created.resolution == "unresolved"


def test_java_edge_persistence_uses_qualified_source_and_target_names() -> None:
    result = parse_java_file(
        "package demo; class Local { int count; void caller() { count = 1; } }",
        "src/demo/Local.java",
    )
    entities = {
        entity.qualified_name: CodeEntity(
            id=index,
            file_path=result.path,
            name=entity.name,
            type=entity.type,
            qualified_name=entity.qualified_name,
        )
        for index, entity in enumerate(result.entities, start=1)
        if entity.qualified_name
    }
    edge = next(edge for edge in result.edges if edge.type == "WRITES")
    row = _build_edge(
        None,
        42,
        result.variant_key,
        edge,
        entities,
        {entity.name.upper(): [entity] for entity in entities.values()},
    )

    assert row is not None
    assert row.src_entity_id == entities[edge.src_name].id
    assert row.dst_entity_id == entities[edge.meta["target_qualified_name"]].id
    assert row.resolution == "resolved"


def test_persisted_java_results_resolve_against_unchanged_other_files() -> None:
    service = parse_java_file(
        "package api; public class Service { public void run(int value) {} }",
        "api/Service.java",
    )
    client = parse_java_file(
        """package app;
import api.Service;
class Client { void call() { new Service().run(1); } }
""",
        "app/Client.java",
    )

    persisted_entities = []
    next_id = 1
    for result in (service, client):
        rows = {}
        for entity in result.entities:
            row = CodeEntity(
                id=next_id,
                source_id=9,
                file_path=result.path,
                variant_key=result.variant_key,
                name=entity.name,
                type=entity.type,
                qualified_name=entity.qualified_name,
                meta_json=entity.meta,
            )
            rows[entity.qualified_name] = row
            persisted_entities.append(row)
            next_id += 1
        for entity in result.entities:
            if entity.parent_qualified_name in rows:
                rows[entity.qualified_name].parent_id = rows[entity.parent_qualified_name].id

    persisted_edges = []
    next_id = 100
    for result in (service, client):
        source_rows = {
            row.qualified_name: row for row in persisted_entities if row.file_path == result.path
        }
        for edge in result.edges:
            source = source_rows[edge.src_name]
            persisted_edges.append(
                CodeEdge(
                    id=next_id,
                    source_id=9,
                    variant_key=result.variant_key,
                    src_entity_id=source.id,
                    dst_name=edge.dst_name,
                    type=edge.type,
                    resolution=edge.resolution,
                    src_start_line=edge.src_start_line,
                    src_end_line=edge.src_end_line,
                    meta_json=edge.meta,
                )
            )
            next_id += 1

    pairs = _java_parse_results(persisted_entities, persisted_edges)
    assert resolve_global_edges(pair[0] for pair in pairs) == 2
    call = next(
        parsed for _, _, parsed_edges in pairs for parsed in parsed_edges if parsed.type == "CALLS"
    )
    assert call.resolution == "resolved"
    assert call.meta["target_qualified_name"] == "api.Service#run(int)"
