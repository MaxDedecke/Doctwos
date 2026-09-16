from __future__ import annotations

import pytest

from java.antlr_bridge import parse_java_source
from java.chunking import chunk_java_source
from java.parse import parse_java_file


def test_java8_declarations_parse_without_diagnostics() -> None:
    result = parse_java_source(
        """package demo;
import java.util.List;
class Box<T extends Number> {
    private final List<T> values;
    Box(List<T> values) { this.values = values; }
    T first() { return values.get(0); }
}
"""
    )

    assert result.diagnostics == ()
    assert result.tree is not None


def test_java21_records_and_guarded_pattern_switch_parse() -> None:
    result = parse_java_source(
        """package demo;
record Pair<T>(T left, T right) {}
class Matcher {
    static String render(Object value) {
        return switch (value) {
            case String text when !text.isBlank() -> text;
            case Pair<?, ?> pair -> pair.toString();
            default -> "";
        };
    }
}
"""
    )

    assert result.diagnostics == ()
    assert result.tree is not None


def test_annotation_value_and_named_pair_predicate() -> None:
    result = parse_java_source("@A(value) class One {}\n@A(value = 1) class Two {}\n")

    assert result.diagnostics == ()


def test_non_final_varargs_record_component_is_rejected() -> None:
    result = parse_java_source("record Invalid(Object... items, Object last) {}")

    assert result.diagnostics


def test_broken_source_keeps_tree_and_caps_diagnostics() -> None:
    source = "\r\n".join("class {" for _ in range(8))

    result = parse_java_source(source, max_diagnostics=2)

    assert result.tree is not None
    assert len(result.diagnostics) == 2
    assert result.diagnostics_truncated is True
    assert result.original_line(result.diagnostics[1].line) == 2


def test_max_diagnostics_must_be_positive() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        parse_java_source("class A {}", max_diagnostics=0)


def test_parse_result_contains_stable_nested_declarations_and_parents() -> None:
    result = parse_java_file(
        """package demo;
class Outer {
    int first, second;
    Outer() {}
    String convert(String value) { return value; }
    int convert(int value) { return value; }
    class Inner {}
    static { int local = 1; }
    { int local = 2; }
}
""",
        "src/demo/Outer.java",
    )
    by_qname = {entity.qualified_name: entity for entity in result.entities}

    assert result.diagnostics == []
    assert by_qname["src/demo/Outer.java"].type == "compilation_unit"
    assert by_qname["src/demo/Outer.java"].meta["is_file_root"] is True
    assert by_qname["demo.Outer"].parent_qualified_name == "demo"
    assert by_qname["demo.Outer.Inner"].parent_qualified_name == "demo.Outer"
    assert by_qname["demo.Outer#first"].parent_qualified_name == "demo.Outer"
    assert "demo.Outer#convert(String)" in by_qname
    assert "demo.Outer#convert(int)" in by_qname
    assert "demo.Outer#<init>()" in by_qname
    assert len([entity for entity in result.entities if entity.type == "initializer"]) == 2


def test_parse_result_records_diagnostics_against_original_crlf_lines() -> None:
    result = parse_java_file(
        "class Broken {\r\n void f() {\r\n  int x = ;\r\n }\r\n}", "Broken.java"
    )

    assert result.diagnostics
    assert result.diagnostics[0].phase == "parser"
    assert result.diagnostics[0].line == 3
    assert result.entities[0].end_line == 5


def test_all_named_type_kinds_and_annotation_elements_are_collected() -> None:
    result = parse_java_file(
        """package types;
public interface Contract { String name(); }
enum State { READY, DONE }
record User(String name) { User { if (name == null) throw new RuntimeException(); } }
@interface Label { String value(); int code() default 0; }
""",
        "types/Types.java",
    )
    by_qname = {entity.qualified_name: entity for entity in result.entities}

    assert result.diagnostics == []
    assert by_qname["types.Contract"].type == "interface"
    assert by_qname["types.State"].type == "enum"
    assert by_qname["types.State#READY"].meta["enum_constant"] is True
    assert by_qname["types.User"].type == "record"
    assert "types.User#<init>(String)" in by_qname
    assert by_qname["types.Label"].type == "annotation_type"
    assert "types.Label#value()" in by_qname
    assert "types.Label#code()" in by_qname


def test_package_and_module_descriptors_are_supported() -> None:
    package_result = parse_java_file("@Deprecated package docs;\n", "package-info.java")
    module_result = parse_java_file(
        "open module demo.app { requires java.base; exports demo.api; }", "module-info.java"
    )

    assert [item.type for item in package_result.entities] == ["compilation_unit", "package"]
    module = next(item for item in module_result.entities if item.type == "module")
    assert module.name == "demo.app"
    assert module.parent_qualified_name == "module-info.java"


def test_maven_module_path_is_attached_to_root_and_nested_entities() -> None:
    result = parse_java_file(
        "package demo; class App { void run() {} }",
        "billing/src/main/java/demo/App.java",
    )

    assert result.entities[0].meta["module"] == "billing"
    assert all(entity.meta["module"] == "billing" for entity in result.entities)


def test_java_chunks_follow_symbols_and_keep_source_context() -> None:
    source = """package demo;
public class Sample {
    public int calculate(int value) {
        return value + 1;
    }
    private int left, right;
}
"""
    result = parse_java_file(source, "Sample.java")
    method_chunk = next(chunk for chunk in result.chunks if chunk.meta["symbol_type"] == "method")
    fields_chunk = next(chunk for chunk in result.chunks if chunk.meta["symbol_type"] == "fields")
    context_chunks = [chunk for chunk in result.chunks if chunk.meta["symbol_type"] == "context"]

    assert method_chunk.meta["symbol_qualified_name"] == "demo.Sample#calculate(int)"
    assert "public int calculate" in method_chunk.content
    assert fields_chunk.meta["symbol_name"] == "left, right"
    assert context_chunks
    assert all(not chunk.meta.get("fallback") for chunk in result.chunks)

    split = chunk_java_source(source, result.entities, chunk_size=30)
    method_parts = [chunk for chunk in split if chunk.meta["symbol_type"] == "method"]
    assert len(method_parts) > 1
    assert [chunk.meta["part"] for chunk in method_parts] == list(range(1, len(method_parts) + 1))


def test_unparseable_source_uses_explicit_text_fallback_chunks() -> None:
    result = parse_java_file("not valid Java at all", "broken.java")

    assert result.diagnostics
    assert result.chunks
    assert all(chunk.meta["fallback"] is True for chunk in result.chunks)


def test_lombok_accessor_annotations_add_source_backed_methods() -> None:
    source = """package lombokdemo;
import lombok.Data;
import lombok.Getter;
import lombok.Setter;
@Data class Person {
    private String name;
    private final int age;
    @Getter(AccessLevel.NONE) private String hidden;
}
class Token {
    @Getter @Setter boolean isValid;
    public boolean isValid() { return isValid; }
}
"""
    result = parse_java_file(source, "Person.java")
    by_qname = {entity.qualified_name: entity for entity in result.entities}

    assert result.diagnostics == []
    assert by_qname["lombokdemo.Person#getName()"].meta["generated_by"] == "lombok"
    assert by_qname["lombokdemo.Person#getAge()"].meta["source_field"] == "lombokdemo.Person#age"
    assert "lombokdemo.Person#setAge(int)" not in by_qname
    assert "lombokdemo.Person#getHidden()" not in by_qname
    assert by_qname["lombokdemo.Token#isValid()"].meta.get("synthetic") is not True
    assert by_qname["lombokdemo.Token#setValid(boolean)"].meta["generated_by"] == "lombok"
