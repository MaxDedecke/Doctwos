"""O-245 regressions motivated by JUnit's engine and utility call sites."""
from java.parse import parse_java_file
from java.resolution import resolve_global_edges


def test_super_override_never_resolves_to_itself():
    result = parse_java_file('class Child extends Parent { void run() { super.run(); } }', 'Child.java')
    resolve_global_edges([result])
    edge = next(e for e in result.edges if e.type == 'CALLS')
    assert edge.resolution == 'unresolved'
    assert edge.meta['resolution_reason'] == 'super_dispatch_requires_hierarchy'


def test_super_call_resolves_to_nearest_non_private_superclass_declaration():
    parent = parse_java_file(
        'package demo; public class Parent { protected void run(int n) {} }',
        'demo/Parent.java',
    )
    child = parse_java_file(
        'package demo; public class Child extends Parent { void run() { super.run(1); } }',
        'demo/Child.java',
    )

    assert resolve_global_edges([parent, child]) == 2
    edge = next(e for e in child.edges if e.type == 'CALLS')
    assert edge.resolution == 'resolved'
    assert edge.meta['target_qualified_name'] == 'demo.Parent#run(int)'
    assert edge.meta['resolution_reason'] == 'current_package'
    assert edge.meta['dispatch_scope'] == 'static_declaration_only'


def test_super_call_walks_an_explicit_superclass_chain_without_using_private_methods():
    base = parse_java_file(
        'package demo; public class Base { void run() {} }', 'demo/Base.java'
    )
    middle = parse_java_file(
        'package demo; public class Middle extends Base {}', 'demo/Middle.java'
    )
    child = parse_java_file(
        'package demo; public class Child extends Middle { void test() { super.run(); } }',
        'demo/Child.java',
    )

    resolve_global_edges([base, middle, child])
    edge = next(e for e in child.edges if e.type == 'CALLS')
    assert edge.resolution == 'resolved'
    assert edge.meta['target_qualified_name'] == 'demo.Base#run()'


def test_cross_package_super_call_does_not_claim_package_private_method():
    parent = parse_java_file(
        'package library; public class Parent { void run() {} }', 'library/Parent.java'
    )
    child = parse_java_file(
        'package client; import library.Parent; class Child extends Parent { '
        'void test() { super.run(); } }',
        'client/Child.java',
    )

    resolve_global_edges([parent, child])
    edge = next(e for e in child.edges if e.type == 'CALLS')
    assert edge.resolution == 'unresolved'
    assert edge.meta['resolution_reason'] == 'super_dispatch_requires_hierarchy'


def test_static_wildcard_owner_is_class_not_package():
    library = parse_java_file(
        'package demo; public class Util { public static void check(int n) {} }', 'demo/Util.java'
    )
    caller = parse_java_file(
        'package client; import static demo.Util.*; class Client { void run() { check(1); } }',
        'client/Client.java',
    )
    resolve_global_edges([library, caller])
    edge = next(e for e in caller.edges if e.type == 'CALLS')
    assert edge.resolution == 'resolved'
    assert edge.meta['target_qualified_name'] == 'demo.Util#check(int)'


def test_interface_field_and_parameter_receivers_resolve_to_declared_interface_method():
    source = """interface Service { void run(); }
class Concrete implements Service { public void run() {} }
class Client { Service service; void test(Service local) { service.run(); local.run(); } }
"""
    result = parse_java_file(source, "Client.java")
    resolve_global_edges([result])
    calls = [e for e in result.edges if e.type == "CALLS"]
    assert len(calls) == 2
    assert all(e.resolution == "resolved" for e in calls)
    assert all(e.meta["target_qualified_name"] == "Service#run()" for e in calls)
    assert {e.meta["resolution_reason"] for e in calls} == {"receiver_field", "receiver_parameter"}


def test_local_variable_and_inherited_receiver_calls_resolve_across_files():
    base = parse_java_file(
        "package api; public class Base { protected void inherited() {} }",
        "api/Base.java",
    )
    service = parse_java_file(
        "package api; public class Service { public void run() {} }",
        "api/Service.java",
    )
    client = parse_java_file(
        """package app;
import api.Base;
import api.Service;
class Client extends Base {
    Service field;
    void test(Service parameter) {
        Service local = parameter;
        parameter.run();
        local.run();
        field.run();
        inherited();
    }
}
""",
        "app/Client.java",
    )

    resolve_global_edges([base, service, client])
    calls = [e for e in client.edges if e.type == "CALLS"]
    assert {e.dst_name for e in calls} == {"parameter.run", "local.run", "field.run", "inherited"}
    targets = {e.dst_name: e.meta.get("target_qualified_name") for e in calls}
    assert targets["parameter.run"] == "api.Service#run()"
    assert targets["local.run"] == "api.Service#run()"
    assert targets["field.run"] == "api.Service#run()"
    assert targets["inherited"] == "api.Base#inherited()"


def test_cross_file_call_with_wrong_arity_stays_open():
    library = parse_java_file(
        "package demo; public class Util { public static void check(int n) {} }", "demo/Util.java"
    )
    caller = parse_java_file(
        "package client; import demo.Util; class Client { void run() { Util.check(); } }",
        "client/Client.java",
    )
    resolve_global_edges([library, caller])
    assert next(e for e in caller.edges if e.type == "CALLS").resolution == "unresolved"


def test_var_local_with_constructor_initializer_resolves_its_receiver_type():
    result = parse_java_file(
        """package demo;
class Service { void run() {} }
class Client {
    void test() {
        var service = new Service();
        service.run();
    }
}
""",
        "demo/Client.java",
    )
    edge = next(e for e in result.edges if e.type == "CALLS")
    assert edge.resolution == "resolved"
    assert edge.meta["target_qualified_name"] == "demo.Service#run()"
    local = next(e for e in result.entities if e.type == "local_variable")
    assert local.meta["inferred_type"] == "Service"
