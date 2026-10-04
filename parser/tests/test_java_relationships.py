from __future__ import annotations

from structure_persist import _build_edge
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

    assert resolve_global_edges([service, client]) == 5
    imports = {edge.dst_name: edge for edge in client.edges if edge.type == "IMPORTS"}
    assert imports["api.Service"].meta["target_qualified_name"] == "api.Service"
    static = imports["api.Service.parse"]
    assert static.resolution == "resolved"
    assert static.meta["target_qualified_name"] == "api.Service"
    assert static.meta["imported_member"] == "parse"
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

    assert resolve_global_edges([first, second, client]) == 3  # explicit type + two package imports
    usages = [edge for edge in client.edges if edge.type == "USES_TYPE"]
    ambiguous = next(edge for edge in usages if edge.dst_name == "Shared")
    explicit = next(edge for edge in usages if edge.dst_name == "one.Shared")
    assert ambiguous.resolution == "unresolved"
    assert ambiguous.meta["resolution_reason"] == "ambiguous_type"
    assert explicit.resolution == "resolved"
    assert explicit.meta["target_qualified_name"] == "one.Shared"
    created = next(edge for edge in client.edges if edge.type == "INSTANTIATES")
    assert created.resolution == "unresolved"


def test_java_global_resolution_keeps_duplicate_maven_types_module_local() -> None:
    module_a = parse_java_file(
        "package duplicate; public class App { public App() {} public void run() {} }",
        "module-a/src/main/java/duplicate/App.java",
    )
    module_b = parse_java_file(
        "package duplicate; public class App { public App() {} public void run() {} }",
        "module-b/src/main/java/duplicate/App.java",
    )
    client = parse_java_file(
        """package client;
import duplicate.App;
class Client { void go() { new App().run(); } }
""",
        "module-a/src/main/java/client/Client.java",
    )

    assert resolve_global_edges([module_a, module_b, client]) == 3
    targets = [edge for edge in client.edges if edge.type in {"INSTANTIATES", "CALLS"}]
    assert all(edge.resolution == "resolved" for edge in targets)
    assert {edge.meta["target_file_path"] for edge in targets} == {
        "module-a/src/main/java/duplicate/App.java"
    }


def test_java_main_sources_never_resolve_to_test_only_types() -> None:
    test_only = parse_java_file(
        "package demo; public class Fixture {}",
        "module-a/src/test/java/demo/Fixture.java",
    )
    main = parse_java_file(
        "package app; import demo.Fixture; class Client { Fixture fixture; }",
        "module-a/src/main/java/app/Client.java",
    )

    assert resolve_global_edges([test_only, main]) == 0
    usage = next(edge for edge in main.edges if edge.type == "USES_TYPE")
    assert usage.resolution == "unresolved"


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
    assert resolve_global_edges(pair[0] for pair in pairs) == 3
    call = next(
        parsed for _, _, parsed_edges in pairs for parsed in parsed_edges if parsed.type == "CALLS"
    )
    assert call.resolution == "resolved"
    assert call.meta["target_qualified_name"] == "api.Service#run(int)"


def test_o365_lambda_and_anonymous_class_call_scope() -> None:
    # 1. Lambda scope
    lambda_src = parse_java_file(
        """package demo;
class A {
    void outer() { Runnable r = () -> helper(); }
    void helper() {}
}
""",
        "demo/A.java",
    )
    resolve_global_edges([lambda_src])
    lambda_calls = [e for e in lambda_src.edges if e.type == "CALLS"]
    assert len(lambda_calls) == 1
    assert "@lambda:" in lambda_calls[0].src_name
    assert lambda_calls[0].resolution == "resolved"
    assert lambda_calls[0].meta["target_qualified_name"] == "demo.A#helper()"

    # 2. Anonymous class method scope
    anon_src = parse_java_file(
        """package demo;
class A {
    interface Job { void run(); }
    void outer() { Job j = new Job() { public void run() { helper(); } }; }
    void helper() {}
}
""",
        "demo/A.java",
    )
    resolve_global_edges([anon_src])
    anon_calls = [e for e in anon_src.edges if e.type == "CALLS"]
    assert len(anon_calls) == 1
    assert "@anonymous:" in anon_calls[0].src_name
    assert anon_calls[0].src_name.endswith("#run()")
    assert anon_calls[0].resolution == "resolved"
    assert anon_calls[0].meta["target_qualified_name"] == "demo.A#helper()"

    # 3. Anonymous class this.helper() binds to anonymous class helper, not outer
    this_src = parse_java_file(
        """package demo;
class A {
    void helper() {}
    void outer() {
        Runnable r = new Runnable() {
            public void run() { this.helper(); }
            void helper() {}
        };
    }
}
""",
        "demo/A.java",
    )
    resolve_global_edges([this_src])
    this_calls = [e for e in this_src.edges if e.type == "CALLS"]
    assert len(this_calls) == 1
    assert "@anonymous:" in this_calls[0].src_name
    assert this_calls[0].resolution == "resolved"
    assert "@anonymous:" in this_calls[0].meta["target_qualified_name"]
    assert this_calls[0].meta["target_qualified_name"].endswith("#helper()")


def test_o366_local_receivers_follow_sibling_block_visibility() -> None:
    result = parse_java_file(
        """package demo;
class Service { void work() {} }
class Client {
    void run() {
        { Service first = new Service(); first.work(); }
        { Service first = new Service(); first.work(); }
    }
}
""",
        "demo/Client.java",
    )

    resolve_global_edges([result])
    calls = [edge for edge in result.edges if edge.type == "CALLS"]
    assert len(calls) == 2
    assert all(edge.resolution == "resolved" for edge in calls)
    assert all(edge.meta["target_qualified_name"] == "demo.Service#work()" for edge in calls)
    assert all(edge.meta["resolution_reason"] == "receiver_local_variable" for edge in calls)


def test_o366_for_catch_and_lambda_receivers_use_visible_declarations() -> None:
    result = parse_java_file(
        """package demo;
class Service { void work() {} }
class Problem extends RuntimeException { void recover() {} }
class Client {
    void run(java.util.List<Service> services) {
        for (Service item : services) item.work();
        try { throw new Problem(); }
        catch (Problem error) { error.recover(); }
        Service captured = new Service();
        Runnable action = () -> captured.work();
    }
}
""",
        "demo/Client.java",
    )

    resolve_global_edges([result])
    calls = [edge for edge in result.edges if edge.type == "CALLS"]
    assert {edge.meta["method_name"] for edge in calls} == {"work", "recover"}
    assert all(edge.resolution == "resolved" for edge in calls)
    assert {edge.meta["target_qualified_name"] for edge in calls} == {
        "demo.Service#work()",
        "demo.Problem#recover()",
    }
    assert {edge.meta["resolution_reason"] for edge in calls} == {
        "receiver_local_variable",
        "receiver_parameter",
    }


def test_o366_use_before_local_declaration_does_not_resolve_forward() -> None:
    result = parse_java_file(
        """package demo;
class Service { void work() {} }
class Client {
    void run() {
        service.work();
        Service service = new Service();
    }
}
""",
        "demo/Client.java",
    )

    resolve_global_edges([result])
    call = next(edge for edge in result.edges if edge.type == "CALLS")
    assert call.resolution == "unresolved"


def test_o367_method_references_resolve_only_unique_repository_targets() -> None:
    result = parse_java_file(
        """package demo;
class Service {
    Service() {}
    void run() {}
    static void start() {}
}
class Client {
    Service service;
    void test() {
        Runnable a = this::local;
        Runnable b = Service::start;
        Runnable c = service::run;
        Runnable d = Service::new;
        Runnable e = this::overloaded;
        Runnable f = System::gc;
    }
    void local() {}
    void overloaded(int value) {}
    void overloaded(String value) {}
}
""",
        "demo/Client.java",
    )

    resolve_global_edges([result])
    references = [edge for edge in result.edges if edge.type == "REFERENCES_METHOD"]
    assert len(references) == 6
    resolved = [edge for edge in references if edge.resolution == "resolved"]
    unresolved = [edge for edge in references if edge.resolution == "unresolved"]
    assert len(resolved) == 4
    assert {edge.meta["target_qualified_name"] for edge in resolved} == {
        "demo.Client#local()",
        "demo.Service#start()",
        "demo.Service#run()",
        "demo.Service#<init>()",
    }
    assert {edge.meta["resolution_reason"] for edge in unresolved} == {
        "ambiguous_method_reference_target",
        "method_reference_target_not_in_repository",
    }


def test_o368_external_receiver_fields_resolve_by_declared_type() -> None:
    result = parse_java_file(
        """package demo;
class Box { int value; }
class Client {
    void test(Box box) {
        box.value = 1;
        int copy = box.value;
    }
}
""",
        "demo/Client.java",
    )

    resolve_global_edges([result])
    accesses = [edge for edge in result.edges if edge.dst_name == "box.value"]
    assert {edge.type for edge in accesses} == {"READS", "WRITES"}
    assert len(accesses) == 2
    assert all(edge.resolution == "resolved" for edge in accesses)
    assert all(edge.meta["target_qualified_name"] == "demo.Box#value" for edge in accesses)
    assert all(edge.meta["receiver_type_qualified_name"] == "demo.Box" for edge in accesses)


def test_o369_call_edges_preserve_try_catch_and_finally_roles() -> None:
    result = parse_java_file(
        """package demo;
class Client {
    void risky() throws IllegalStateException {}
    void recover() {}
    void close() {}
    void run() {
        try { risky(); }
        catch (IllegalStateException error) { recover(); }
        finally { close(); }
    }
}
""",
        "demo/Client.java",
    )

    method = "demo.Client#run()"
    calls = [edge for edge in result.edges if edge.type == "CALLS" and edge.src_name == method]
    by_name = {edge.meta["method_name"]: edge for edge in calls}
    assert by_name["risky"].meta["control_role"] == "try_body"
    risky = next(entity for entity in result.entities if entity.qualified_name == "demo.Client#risky()")
    assert risky.meta["throws_types"] == ["IllegalStateException"]
    assert by_name["recover"].meta["control_role"] == "exception_handler"
    assert by_name["recover"].meta["control_context"] == "catch(IllegalStateException)"
    assert by_name["recover"].meta["exception_types"] == ["IllegalStateException"]
    assert by_name["close"].meta["control_role"] == "cleanup"
    assert by_name["close"].meta["control_context"] == "finally"


def test_call_edges_carry_control_path_for_conditions_loops_and_switch() -> None:
    result = parse_java_file(
        """package demo;
class Flow {
    void a() {} void b() {} void c() {} void d() {} void e() {} void f() {} void g() {}
    void run(boolean ok, int mode, java.util.List<String> items) {
        if (ok) { a(); } else { b(); }
        for (String item : items) { c(); }
        while (mode > 0) { if (mode == 2) { d(); } }
        switch (mode) { case 1: e(); break; default: f(); }
        g();
        Runnable r = () -> { if (ok) { a(); } };
    }
}
""",
        "demo/Flow.java",
    )
    calls = [edge for edge in result.edges if edge.type == "CALLS" and edge.src_name.startswith("demo.Flow#run(")]
    by_name = {edge.meta["method_name"]: edge for edge in calls if edge.meta["method_name"] != "a"}
    path = lambda name: by_name[name].meta.get("control_path")  # noqa: E731

    first_a = next(edge for edge in calls if edge.meta["method_name"] == "a")
    assert first_a.meta["control_path"] == [{"type": "IF", "branch": "THEN", "condition": "ok"}]
    assert path("b") == [{"type": "IF", "branch": "ELSE", "condition": "ok"}]
    assert path("c") == [{"type": "LOOP", "kind": "FOR_EACH", "text": "String item : items"}]
    assert path("d") == [
        {"type": "LOOP", "kind": "WHILE", "text": "mode > 0"},
        {"type": "IF", "branch": "THEN", "condition": "mode == 2"},
    ]
    assert path("e") == [{"type": "SWITCH", "branch": "CASE", "subject": "mode", "when": "case 1"}]
    assert path("f") == [{"type": "SWITCH", "branch": "CASE", "subject": "mode", "when": "default"}]
    assert path("g") is None


def test_java_imports_resolve_to_repository_types_and_packages_only() -> None:
    api = parse_java_file("package api; public class Service { static int parse() { return 1; } }\n", "api/Service.java")
    client = parse_java_file(
        """package app;
import api.Service;
import api.*;
import static api.Service.*;
import java.util.List;
import org.slf4j.Logger;
class Client {}
""",
        "app/Client.java",
    )

    resolve_global_edges([api, client])
    imports = {edge.dst_name: edge for edge in client.edges if edge.type == "IMPORTS"}
    assert imports["api.Service"].resolution == "resolved"
    assert imports["api.*"].resolution == "resolved"
    assert imports["api.*"].meta["target_qualified_name"] == "api"
    assert imports["api.Service.*"].meta["target_qualified_name"] == "api.Service"
    assert imports["java.util.List"].resolution == "unresolved"
    assert imports["org.slf4j.Logger"].resolution == "unresolved"


def test_overload_is_chosen_from_inferred_argument_types():
    """O-309: `List.of(...)`, Casts, `X.class` und `"a" + b` liefern belegbare Argumenttypen für die Überladungswahl."""
    source = (
        "package app;\n"
        "import java.util.List;\n"
        "class Panel {\n"
        "  void setChoices(List<String> choices) {}\n"
        "  void setChoices(IModel<String> model) {}\n"
        "  void put(Class<?> type) {}\n"
        "  void put(String name) {}\n"
        "  void run(Object o) {\n"
        "    setChoices(List.of(\"a\"));\n"
        "    put(Panel.class);\n"
        "    put(\"x\" + o);\n"
        "    setChoices(o);\n"
        "    setChoices(List.of(\"a\").get(0));\n"
        "  }\n"
        "}\n"
    )
    result = parse_java_file(source, "app/Panel.java")
    resolve_global_edges([result])
    calls = {(e.src_start_line, e.dst_name): e for e in result.edges if e.type == "CALLS"}
    assert calls[(9, "setChoices")].meta["target_qualified_name"] == "app.Panel#setChoices(List<String>)"
    assert calls[(10, "put")].meta["target_qualified_name"] == "app.Panel#put(Class<?>)"
    assert calls[(11, "put")].meta["target_qualified_name"] == "app.Panel#put(String)"
    assert calls[(12, "setChoices")].resolution == "unresolved"  # `o` hat keinen belegbaren Typ
    assert calls[(13, "setChoices")].resolution == "unresolved"  # `.get(0)` ist nicht die Fabrik selbst
