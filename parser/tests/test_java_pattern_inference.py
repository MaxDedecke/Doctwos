from java.parse import parse_java_file
from java.resolution import resolve_global_edges


def calls(result, name):
    return [
        edge
        for edge in result.edges
        if edge.type == "CALLS" and edge.meta.get("method_name") == name
    ]


def test_pattern_bindings_are_flow_scoped_and_do_not_leak_into_else_or_after_if():
    result = parse_java_file(
        """class Service {void run(){} boolean ok(){return true;}}
class C {void use(Object x){
  if(x instanceof Service s && s.ok()) {s.run();} else {s.run();}
  s.run();
}}""",
        "C.java",
    )
    assert not result.diagnostics
    binding = next(entity for entity in result.entities if entity.meta.get("pattern_binding"))
    assert binding.meta["variable_type"] == "Service"
    assert calls(result, "ok")[0].meta["target_qualified_name"] == "Service#ok()"
    assert [edge.resolution for edge in calls(result, "run")] == [
        "resolved",
        "unresolved",
        "unresolved",
    ]


def test_negated_guard_return_and_switch_guard_preserve_binding_scope():
    result = parse_java_file(
        """class Service {void run(){} boolean ok(){return true;}}
class C {
 void a(Object x){if(!(x instanceof Service s)) return; s.run();}
 void b(Object x){switch(x){case Service s when s.ok()->s.run();default->s.run();}}
}""",
        "C.java",
    )
    assert not result.diagnostics
    assert [edge.resolution for edge in calls(result, "run")] == [
        "resolved",
        "resolved",
        "unresolved",
    ]
    assert calls(result, "ok")[0].resolution == "resolved"


def test_boolean_function_does_not_prove_a_pattern_matches():
    result = parse_java_file(
        """class Service{void run(){}}
class C {boolean check(boolean x){return true;}
void use(Object x){if(check(x instanceof Service s)){s.run();}}}""",
        "C.java",
    )
    assert not result.diagnostics
    assert calls(result, "run")[0].resolution == "unresolved"


def test_or_rhs_only_has_binding_when_left_false_proves_match():
    result = parse_java_file(
        """class Service {boolean ok(){return true;} void run(){}}
class C {void use(Object x){
 if(!(x instanceof Service s) || s.ok()) {} else {s.run();}
 if(x instanceof Service t || t.ok()) {t.run();}
}}""",
        "C.java",
    )
    assert not result.diagnostics
    assert [edge.resolution for edge in calls(result, "ok")] == ["resolved", "unresolved"]
    assert [edge.resolution for edge in calls(result, "run")] == ["resolved", "unresolved"]


def test_factory_var_uses_return_type_in_factory_package():
    service = parse_java_file(
        "package api; public class Service {public void run(){}}", "api/Service.java"
    )
    factory = parse_java_file(
        "package api; public class Factory {public static Service make(){return new Service();}}",
        "api/Factory.java",
    )
    client = parse_java_file(
        "package client; import api.Factory; class C {void use(){var s=Factory.make(); s.run();}}",
        "client/C.java",
    )
    resolve_global_edges([client, factory, service])
    edge = calls(client, "run")[0]
    assert edge.resolution == "resolved"
    assert edge.meta["target_qualified_name"] == "api.Service#run()"


def test_factory_initializers_on_one_line_do_not_share_return_types():
    result = parse_java_file(
        """class A {void run(){}} class B {void run(){}}
class C {A a(){return new A();} B b(){return new B();}
void use(){var first=a(); var second=b(); first.run(); second.run();}}""",
        "C.java",
    )
    assert not result.diagnostics
    assert [edge.meta.get("target_qualified_name") for edge in calls(result, "run")] == [
        "A#run()",
        "B#run()",
    ]


def test_factory_inference_does_not_choose_an_unrelated_call_in_conditional_initializer():
    result = parse_java_file(
        """class A {void run(){}} class B {void run(){}}
class C {A a(){return new A();} B b(){return new B();}
void use(boolean flag){a(); var value=flag?a():b(); value.run();}}""",
        "C.java",
    )
    assert not result.diagnostics
    assert calls(result, "run")[0].resolution == "unresolved"


def methods(result):
    return sorted(entity.name for entity in result.entities if entity.type == "method")


def bindings(result):
    return {
        (entity.parent_name, entity.name): entity.meta
        for entity in result.entities
        if entity.meta.get("pattern_binding")
    }


def test_var_record_patterns_parse_without_losing_following_members():
    result = parse_java_file(
        """record Circle(double r) {}
record Rect(double w, double h) {}
record Box(Object content, Object label) {}
class C {
 double rule(Object x){return switch(x){case Circle(var r)->r; case Box(Circle(var r), _)->r; default->0;};}
 double colon(Object x){switch(x){case Rect(final var w, double h): return w*h; default: return 0;}}
 double test(Object x){if(x instanceof Rect(var w, var h)) return w*h; return 0;}
 int match(Object x){return switch(x){case Box(_, var label)->1; case Box(_, _)->2; default->0;};}
 int after(){return 1;}
}""",
        "C.java",
    )
    assert not result.diagnostics
    assert {"rule", "colon", "test", "match", "after"} <= set(methods(result))
    declared = bindings(result)
    width = declared[("colon", "w")]
    assert width["variable_type"] == "var"
    assert (width["record_pattern_type"], width["record_component_index"]) == ("Rect", 0)
    assert declared[("colon", "h")]["variable_type"] == "double"
    assert "record_pattern_type" not in declared[("colon", "h")]
    assert declared[("test", "h")]["record_component_index"] == 1
    label = declared[("match", "label")]
    assert (label["record_pattern_type"], label["record_component_index"]) == ("Box", 1)
    nested = [
        entity.meta
        for entity in result.entities
        if entity.meta.get("pattern_binding") and entity.name == "r"
    ]
    assert [item["record_pattern_type"] for item in nested] == ["Circle", "Circle"]


def test_var_record_component_receiver_uses_the_component_type_from_the_record_file():
    point = parse_java_file(
        """package geo;
public record Point(double x, double y) {
  public double distanceTo(Point other){return 0;}
}""",
        "geo/Point.java",
    )
    line = parse_java_file(
        "package geo; public record Line(Point start, Point end) {}", "geo/Line.java"
    )
    pair = parse_java_file(
        "package geo; public record Pair<A, B>(A first, B second) {}", "geo/Pair.java"
    )
    client = parse_java_file(
        """package app;
import geo.Line;
import geo.Pair;
class C {
 double a(Object o){return switch(o){case Line(var start, var end)->start.distanceTo(end); default->0;};}
 double b(Object o){if(o instanceof Line(Point(var x, var y), var end)) return end.distanceTo(end); return 0;}
 int c(Object o){if(o instanceof Pair<?, ?>(var first, var second)) return first.distanceTo(null); return 0;}
}""",
        "app/C.java",
    )
    assert not client.diagnostics
    resolve_global_edges([client, line, pair, point])
    edges = calls(client, "distanceTo")
    assert [edge.meta.get("target_qualified_name") for edge in edges[:2]] == [
        "geo.Point#distanceTo(Point)",
        "geo.Point#distanceTo(Point)",
    ]
    assert edges[0].meta["resolution_reason"] == "record_component_type"
    # A component typed by a record type parameter is left unresolved instead of guessed.
    assert edges[2].resolution == "unresolved"
