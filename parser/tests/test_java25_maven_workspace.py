from types import SimpleNamespace

from java.parse import parse_java_file
from java.resolution import resolve_global_edges
from maven.model import effective_models, read_model
from maven.workspace import apply_maven_scopes


def project(path, source):
    return SimpleNamespace(file_path=path, meta_json={"maven_model": read_model(source)})


def test_java25_compact_sources_keep_method_ownership_calls_and_physical_lines():
    result = parse_java_file(
        "import module java.base;\nvoid main() { work(); }\nvoid work() {}",
        "app/src/main/java/Hello.java",
    )
    assert not result.diagnostics
    main = next(e for e in result.entities if e.name == "main")
    assert main.qualified_name == "Hello#main()"
    assert main.start_line == 2
    call = next(e for e in result.edges if e.type == "CALLS")
    assert call.meta["target_qualified_name"] == "Hello#work()"
    assert any(e.type == "IMPORTS_MODULE" and e.dst_name == "java.base" for e in result.edges)


def test_java25_flexible_constructor_body_and_repository_module_import():
    constructor = parse_java_file(
        "class Base { Base(int n) {} } class Child extends Base { Child(int n) { int checked = n; super(checked); } }",
        "Child.java",
    )
    assert not constructor.diagnostics
    descriptor = parse_java_file(
        "module example.api { exports api; }", "api/src/main/java/module-info.java"
    )
    api = parse_java_file(
        "package api; public class Orders { public static void send() {} }",
        "api/src/main/java/api/Orders.java",
    )
    client = parse_java_file(
        "import module example.api; class Client { void run() { Orders.send(); } }",
        "client/src/main/java/Client.java",
    )
    resolve_global_edges([descriptor, api, client])
    call = next(e for e in client.edges if e.type == "CALLS")
    assert call.meta["target_qualified_name"] == "api.Orders#send()"


def test_reactor_classpath_prevents_unrelated_module_calls_and_honors_test_scope():
    api = parse_java_file(
        "package api; public class Orders { public static void send() {} }",
        "api/src/main/java/api/Orders.java",
    )

    def client(path):
        return parse_java_file(
            "import api.Orders; class Client { void run() { Orders.send(); } }", path
        )

    main, test = (
        client("client/src/main/java/Client.java"),
        client("client/src/test/java/Client.java"),
    )
    projects = [
        project(
            "api/pom.xml",
            "<project><groupId>x</groupId><artifactId>api</artifactId><version>1</version></project>",
        ),
        project(
            "client/pom.xml",
            "<project><groupId>x</groupId><artifactId>client</artifactId><dependencies><dependency><groupId>x</groupId><artifactId>api</artifactId><scope>test</scope></dependency></dependencies></project>",
        ),
    ]
    apply_maven_scopes([api, main, test], projects)
    resolve_global_edges([api, main, test])
    assert next(e for e in main.edges if e.type == "CALLS").resolution != "resolved"
    assert (
        next(e for e in test.edges if e.type == "CALLS").meta["target_qualified_name"]
        == "api.Orders#send()"
    )


def test_parent_properties_management_and_explicit_profiles_resolve_without_a_build():
    models = {
        "pom.xml": read_model(
            """<project><groupId>x</groupId><artifactId>parent</artifactId><version>25</version><properties><api.version>2</api.version></properties><dependencyManagement><dependencies><dependency><groupId>x</groupId><artifactId>api</artifactId><version>${api.version}</version></dependency></dependencies></dependencyManagement></project>"""
        ),
        "app/pom.xml": read_model(
            """<project><parent><groupId>x</groupId><artifactId>parent</artifactId><version>25</version></parent><artifactId>app</artifactId><profiles><profile><id>soap</id><dependencies><dependency><groupId>x</groupId><artifactId>api</artifactId></dependency></dependencies></profile></profiles></project>"""
        ),
    }
    model = effective_models(models, active_profiles=["soap"])["app/pom.xml"]
    assert model["groupId"] == "x" and model["version"] == "25"
    assert model["dependencies"][0]["version"] == "2"
    assert not model["issues"]
    assert not effective_models(models)["app/pom.xml"]["dependencies"]


def test_cyclic_parents_are_reported_and_do_not_loop():
    models = {
        "a/pom.xml": read_model(
            "<project><artifactId>a</artifactId><parent><artifactId>b</artifactId><relativePath>../b/pom.xml</relativePath></parent></project>"
        ),
        "b/pom.xml": read_model(
            "<project><artifactId>b</artifactId><parent><artifactId>a</artifactId><relativePath>../a/pom.xml</relativePath></parent></project>"
        ),
    }
    assert effective_models(models)["a/pom.xml"]["issues"]


def test_pom_change_invalidates_a_resolved_call_and_dependency_test_classes_stay_hidden():
    api = parse_java_file(
        "package api; public class Orders { public static void send() {} }",
        "api/src/main/java/api/Orders.java",
    )
    helper = parse_java_file(
        "package api; public class Helper {}", "api/src/test/java/api/Helper.java"
    )
    client = parse_java_file(
        "import api.Orders; import api.Helper; class Client { void run() { Orders.send(); } Helper helper; }",
        "client/src/test/java/Client.java",
    )
    available = project(
        "api/pom.xml", "<project><groupId>x</groupId><artifactId>api</artifactId></project>"
    )
    allowed = project(
        "client/pom.xml",
        "<project><groupId>x</groupId><artifactId>client</artifactId><dependencies><dependency><groupId>x</groupId><artifactId>api</artifactId></dependency></dependencies></project>",
    )
    apply_maven_scopes([api, helper, client], [available, allowed])
    resolve_global_edges([api, helper, client])
    assert next(e for e in client.edges if e.type == "CALLS").resolution == "resolved"
    assert not any(e.resolution == "resolved" for e in client.edges if e.dst_name == "api.Helper")
    denied = project(
        "client/pom.xml", "<project><groupId>x</groupId><artifactId>client</artifactId></project>"
    )
    apply_maven_scopes([api, helper, client], [available, denied])
    resolve_global_edges([api, helper, client])
    assert next(e for e in client.edges if e.type == "CALLS").resolution != "resolved"


def test_default_profile_is_local_to_its_pom_and_parent_coordinates_are_checked():
    model = read_model(
        "<project><artifactId>app</artifactId><profiles><profile><id>defaults</id><activation><activeByDefault>true</activeByDefault></activation><properties><label>default</label></properties></profile></profiles></project>"
    )
    assert (
        effective_models({"pom.xml": model}, active_profiles=["other-module-profile"])["pom.xml"][
            "properties"
        ]["label"]
        == "default"
    )
    parent = read_model(
        "<project><groupId>x</groupId><artifactId>parent</artifactId><version>2</version><properties><unexpected>wrong</unexpected></properties></project>"
    )
    child = read_model(
        "<project><artifactId>app</artifactId><parent><groupId>x</groupId><artifactId>parent</artifactId><version>1</version></parent></project>"
    )
    resolved = effective_models({"pom.xml": parent, "app/pom.xml": child})["app/pom.xml"]
    assert resolved["issues"] and "unexpected" not in resolved["properties"]
