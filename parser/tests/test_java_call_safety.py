"""O-245 regressions motivated by JUnit's engine and utility call sites."""
from java.parse import parse_java_file
from java.resolution import resolve_global_edges


def test_super_override_never_resolves_to_itself():
    result = parse_java_file('class Child extends Parent { void run() { super.run(); } }', 'Child.java')
    resolve_global_edges([result])
    edge = next(e for e in result.edges if e.type == 'CALLS')
    assert edge.resolution == 'unresolved'
    assert edge.meta['resolution_reason'] == 'super_dispatch_requires_hierarchy'


def test_static_wildcard_owner_is_class_not_package():
    library = parse_java_file('package demo; public class Util { public static void check(int n) {} }', 'demo/Util.java')
    caller = parse_java_file('package client; import static demo.Util.*; class Client { void run() { check(1); } }', 'client/Client.java')
    resolve_global_edges([library, caller])
    edge = next(e for e in caller.edges if e.type == 'CALLS')
    assert edge.resolution == 'resolved'
    assert edge.meta['target_qualified_name'] == 'demo.Util#check(int)'


def test_interface_field_and_local_receivers_do_not_guess_by_method_name():
    source = '''interface Service { void run(); }
class Concrete implements Service { public void run() {} }
class Client { Service service; void test(Service local) { service.run(); local.run(); } }
'''
    result = parse_java_file(source, 'Client.java')
    resolve_global_edges([result])
    calls = [e for e in result.edges if e.type == 'CALLS']
    assert len(calls) == 2
    assert all(e.resolution == 'unresolved' for e in calls)
    assert all(e.meta['resolution_reason'] == 'receiver_or_classpath_not_resolved' for e in calls)


def test_cross_file_call_with_wrong_arity_stays_open():
    library = parse_java_file('package demo; public class Util { public static void check(int n) {} }', 'demo/Util.java')
    caller = parse_java_file('package client; import demo.Util; class Client { void run() { Util.check(); } }', 'client/Client.java')
    resolve_global_edges([library, caller])
    assert next(e for e in caller.edges if e.type == 'CALLS').resolution == 'unresolved'
