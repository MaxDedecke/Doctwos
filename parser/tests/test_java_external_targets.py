"""O-377: belegt externe Java-Ziele (JDK, Bibliotheken, statische Importe) werden gekennzeichnet."""

from java.parse import parse_java_file
from java.resolution import resolve_global_edges

SERVICE = "package api; public class Service { public static int parse(int v) { return v; } }\n"

CLIENT = """package app;
import api.Service;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;
class Client {
    private static final Logger LOG = LoggerFactory.getLogger(Client.class);
    private final Optional<String> maybe = Optional.empty();
    void run(List<String> items, Service service) {
        LOG.error("x");
        List.of(1);
        assertEquals(1, 2);
        verify(items);
        service.unknown();
        String.valueOf(1);
        missing();
        items.add("a");
    }
}
"""


def _edges():
    client = parse_java_file(CLIENT, "app/Client.java")
    resolve_global_edges([parse_java_file(SERVICE, "api/Service.java"), client])
    return client


def _call(client, dst):
    return next(e for e in client.edges if e.type == "CALLS" and e.dst_name == dst)


def _imports(client):
    return {e.dst_name: e for e in client.edges if e.type == "IMPORTS"}


def test_receiver_calls_are_marked_by_declared_type_or_type_name():
    client = _edges()
    log = _call(client, "LOG.error").meta["external"]
    assert (log["category"], log["library"], log["via"]) == ("library", "org.slf4j.Logger", "declared_receiver_type")
    listed = _call(client, "List.of").meta["external"]
    assert (listed["category"], listed["library"]) == ("jdk", "java.util.List")
    assert _call(client, "String.valueOf").meta["external"]["library"] == "java.lang.String"
    assert _call(client, "items.add").meta["external"]["library"] == "java.util.List"


def test_static_imports_are_explicit_certain_and_wildcards_only_possible():
    client = _edges()
    explicit = _call(client, "assertEquals").meta["external"]
    assert (explicit["library"], explicit["via"]) == ("org.junit.jupiter.api.Assertions", "static_import")
    assert "certainty" not in explicit
    wildcard = _call(client, "verify").meta["external"]
    assert (wildcard["library"], wildcard["via"], wildcard["certainty"]) == (
        "org.mockito.Mockito", "static_wildcard_import", "possible",
    )


def test_real_gaps_and_repository_targets_are_not_marked_external():
    client = _edges()
    assert "external" not in _call(client, "service.unknown").meta  # Typ liegt im Repository
    imports = _imports(client)
    assert imports["api.Service"].resolution == "resolved"
    assert "external" not in imports["api.Service"].meta
    assert imports["java.util.List"].meta["external"]["category"] == "jdk"
    assert imports["org.slf4j.Logger"].meta["external"]["category"] == "library"


def test_stale_external_flag_is_removed_once_an_edge_resolves():
    client = parse_java_file("package app; import api.Service; class C { Service s; }", "app/C.java")
    usage = next(e for e in client.edges if e.type == "USES_TYPE")
    usage.meta["external"] = {"category": "library", "library": "old.Service"}
    resolve_global_edges([parse_java_file(SERVICE, "api/Service.java"), client])
    assert usage.resolution == "resolved"
    assert "external" not in usage.meta


def test_unqualified_call_without_any_static_import_is_not_marked():
    client = parse_java_file("package app; class C { void run() { missing(); } }", "app/C.java")
    resolve_global_edges([client])
    assert "external" not in next(e for e in client.edges if e.type == "CALLS").meta


def test_static_field_reads_and_method_references_on_external_types_are_marked():
    client = parse_java_file(
        """package app;
import org.apache.commons.lang3.StringUtils;
import java.util.stream.Stream;
class C {
    String run(Stream<String> s) {
        s.filter(StringUtils::isNotBlank);
        return StringUtils.EMPTY;
    }
}
""",
        "app/C.java",
    )
    resolve_global_edges([client])
    read = next(e for e in client.edges if e.type == "READS" and e.dst_name == "StringUtils.EMPTY")
    assert read.meta["external"]["library"] == "org.apache.commons.lang3.StringUtils"
    reference = next(e for e in client.edges if e.type == "REFERENCES_METHOD")
    assert reference.meta["external"]["library"] == "org.apache.commons.lang3.StringUtils"


GENERIC = """package app;
import java.util.List;
class Box<T> extends Base {
    private T value;
    Box(String id, int n) { super(id, n); }
    Box() { this("x", 1); }
    <E> List<E> wrap(E item) { return List.of(item); }
}
class Base { Base(String id, int n) {} }
"""


def test_type_variables_are_not_counted_as_open_gaps():
    box = parse_java_file(GENERIC, "app/Box.java")
    resolve_global_edges([box])
    variables = [e for e in box.edges if e.type == "USES_TYPE" and e.dst_name in {"T", "E"}]
    assert variables
    assert all(e.meta["external"]["category"] == "type_parameter" for e in variables)


def test_constructor_delegation_keeps_a_clean_target_name():
    box = parse_java_file(GENERIC, "app/Box.java")
    names = {e.dst_name for e in box.edges if e.type == "CALLS"}
    assert {"super", "this"} <= names
    assert not any(name.startswith(("super(", "this(")) for name in names)
