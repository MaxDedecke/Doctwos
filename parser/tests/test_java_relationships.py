from __future__ import annotations

from java.parse import parse_java_file


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
    assert next(edge for edge in writes if edge.dst_name == "other.value").resolution == "unresolved"
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
