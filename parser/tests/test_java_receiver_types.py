from java.parse import parse_java_file
from java.resolution import resolve_global_edges


def targets(result, method="run"):
    return [
        edge
        for edge in result.edges
        if edge.type == "CALLS" and edge.meta.get("method_name") == method
    ]


def test_record_accessors_have_declaration_locations_and_do_not_duplicate_explicit_methods():
    result = parse_java_file(
        """record Person(String name, int age) {
  public String name(){return name;}
}
class C {int use(Person p){p.name(); return p.age();}}""",
        "C.java",
    )
    assert not result.diagnostics
    accessors = [
        entity
        for entity in result.entities
        if entity.type == "method" and entity.parent_qualified_name == "Person"
    ]
    assert sorted(entity.name for entity in accessors) == ["age", "name"]
    generated = next(entity for entity in accessors if entity.name == "age")
    assert generated.start_line == 1
    assert generated.meta["generated_by"] == "record"
    assert generated.meta["source_component"] == "Person#component:age"
    assert not next(entity for entity in accessors if entity.name == "name").meta.get("synthetic")
    assert targets(result, "name")[0].meta["target_qualified_name"] == "Person#name()"
    assert targets(result, "age")[0].meta["target_qualified_name"] == "Person#age()"


def test_generic_return_type_is_specialized_in_the_receiver_import_context():
    box = parse_java_file(
        "package box; public class Box<T>{public T get(){return null;}}", "box/Box.java"
    )
    service = parse_java_file(
        "package service; public class Service{public void run(){}}", "service/Service.java"
    )
    client = parse_java_file(
        "package app; import box.Box; import service.Service; class C{void use(Box<Service> b){b.get().run();}}",
        "app/C.java",
    )
    resolve_global_edges([box, service, client])
    assert targets(client)[0].meta["target_qualified_name"] == "service.Service#run()"


def test_method_generic_parameter_does_not_inherit_the_class_parameter_binding():
    result = parse_java_file(
        """class Service{void run(){}}
class Box<T>{<T> T get(){return null;}}
class C{void use(Box<Service> b){b.get().run();}}""",
        "C.java",
    )
    assert not result.diagnostics
    assert targets(result)[0].resolution == "unresolved"


def test_array_receivers_require_the_correct_number_of_dimensions():
    result = parse_java_file(
        """class Service{void run(){}}
class C{Service[] field; void use(Service[] one,Service[][] two,Service scalar){
 one[0].run(); two[0][0].run(); this.field[1].run();
 two[0].run(); scalar[0].run();
}}""",
        "C.java",
    )
    assert not result.diagnostics
    edges = targets(result)
    assert [edge.resolution for edge in edges] == ["resolved"] * 3 + ["unresolved"] * 2
    assert all(edge.meta["target_qualified_name"] == "Service#run()" for edge in edges[:3])
