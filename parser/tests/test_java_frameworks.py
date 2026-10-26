from java.parse import parse_java_file
from java.resolution import resolve_global_edges
from java.injection import derive_injection_edges


def parse(source, path="app/src/main/java/app/Test.java"):
    return parse_java_file(source, path)


def test_spring_endpoint_combines_class_method_paths_and_parameter_binding():
    result = parse("""package app;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/orders") class Orders {
 @GetMapping(value={"/{id}", "/by-id/{id}"}, produces="application/json")
 public String read(@PathVariable("id") String id) { return id; }
}""")
    endpoints = [e for e in result.entities if e.type == "endpoint"]
    assert {e.meta["path"] for e in endpoints} == {"/orders/{id}", "/orders/by-id/{id}"}
    assert all(e.meta["http_method"] == "GET" and e.start_line == 4 for e in endpoints)
    assert endpoints[0].meta["parameters"][0]["annotations"][0]["name"] == "PathVariable"
    assert len([e for e in result.edges if e.type == "EXPOSES"]) == 2


def test_jaxrs_and_spring_ws_endpoints_have_separate_transport_facts():
    rest = parse(
        """import jakarta.ws.rs.*; @Path("/api") class API { @GET @Path("/status") public String status() { return "ok"; } }"""
    )
    endpoint = next(e for e in rest.entities if e.type == "endpoint")
    assert endpoint.meta["path"] == "/api/status" and endpoint.meta["framework"] == "jaxrs"
    soap = parse(
        """import org.springframework.ws.server.endpoint.annotation.*; @Endpoint class API { @PayloadRoot(namespace="urn:orders", localPart="Submit") public String submit(String request) { return request; } }"""
    )
    endpoint = next(e for e in soap.entities if e.type == "endpoint")
    assert endpoint.meta["namespace"] == "urn:orders" and endpoint.meta["operation"] == "Submit"


def test_jaxws_webmethods_and_exclusion():
    result = parse(
        """import jakarta.jws.*; @WebService(serviceName="Orders", targetNamespace="urn:orders") class API { @WebMethod(operationName="submit") public void send() {} @WebMethod(exclude=true) public void internal() {} }"""
    )
    endpoints = [e for e in result.entities if e.type == "endpoint"]
    assert len(endpoints) == 1 and endpoints[0].meta["operation"] == "submit"


def test_named_cdi_injection_selects_implementation_without_overwriting_static_call():
    result = parse("""import jakarta.inject.*; import jakarta.enterprise.context.*;
interface Port { void send(); }
@ApplicationScoped @Named("fast") class Fast implements Port { public void send() {} }
@ApplicationScoped @Named("slow") class Slow implements Port { public void send() {} }
class Client { @Inject @Named("fast") Port port; void run() { port.send(); } }""")
    derived = [e for _, e in derive_injection_edges([result])]
    injection = next(e for e in derived if e.type == "INJECTS")
    assert injection.meta["target_qualified_name"] == "Fast"
    dispatch = next(e for e in derived if e.type == "DISPATCHES_TO")
    assert dispatch.meta["target_qualified_name"] == "Fast#send()"
    assert (
        next(e for e in result.edges if e.type == "CALLS").meta["target_qualified_name"]
        == "Port#send()"
    )


def test_single_spring_constructor_primary_qualifier_and_assignment():
    result = parse("""import org.springframework.stereotype.*; import org.springframework.beans.factory.annotation.*; import org.springframework.context.annotation.*;
interface Port { void send(); }
@Service @Primary class Fast implements Port { public void send() {} }
@Service("slow") class Slow implements Port { public void send() {} }
@Component class Client { private final Port port; Client(Port port) { this.port = port; } void run() { port.send(); } }""")
    derived = [e for _, e in derive_injection_edges([result])]
    assert next(e for e in derived if e.type == "INJECTS").meta["target_qualified_name"] == "Fast"
    assert (
        next(e for e in derived if e.type == "DISPATCHES_TO").meta["target_qualified_name"]
        == "Fast#send()"
    )


def test_setter_injection_retains_parameter_qualifier_and_is_ambiguous_without_it():
    result = parse("""import org.springframework.stereotype.*; import org.springframework.beans.factory.annotation.*;
interface Port {}
@Service("fast") class Fast implements Port {} @Service("slow") class Slow implements Port {}
class Client { @Autowired void configure(@Qualifier("slow") Port port) {} @Autowired Port unresolved; }""")
    derived = [e for _, e in derive_injection_edges([result]) if e.type == "INJECTS"]
    setter = next(e for e in derived if "@param:" in e.src_name)
    assert setter.meta["target_qualified_name"] == "Slow"
    ambiguous = next(e for e in derived if e.src_name == "Client#unresolved")
    assert ambiguous.resolution == "unresolved" and ambiguous.meta["candidate_count"] == 2


def test_producer_and_profiles_are_explicit_candidates(monkeypatch):
    result = parse("""import org.springframework.context.annotation.*; import org.springframework.beans.factory.annotation.*;
interface Port {} @Configuration class Config { @Bean("fast") Port port() { return null; } }
class Client { @Autowired @Qualifier("fast") Port port; }""")
    derived = [e for _, e in derive_injection_edges([result]) if e.type == "INJECTS"]
    assert derived[0].meta["target_qualified_name"] == "Config#port()"
    monkeypatch.setenv("DOCTUS_SPRING_PROFILES", "prod")
    profiled = parse("""import org.springframework.stereotype.*; import org.springframework.context.annotation.*; import org.springframework.beans.factory.annotation.*;
interface Port {} @Service @Profile("dev") class Dev implements Port {} class Client { @Autowired Port port; }""")
    assert (
        next(e for _, e in derive_injection_edges([profiled]) if e.type == "INJECTS").resolution
        == "unresolved"
    )


def test_cross_file_injection_uses_imports_and_maven_visibility():
    api = parse(
        "package api; public interface Port { void send(); }", "api/src/main/java/api/Port.java"
    )
    bean = parse(
        "package impl; import api.Port; import jakarta.enterprise.context.ApplicationScoped; @ApplicationScoped public class Fast implements Port { public void send() {} }",
        "impl/src/main/java/impl/Fast.java",
    )
    client = parse(
        "package client; import api.Port; import jakarta.inject.Inject; class Client { @Inject Port port; void run() { port.send(); } }",
        "client/src/main/java/client/Client.java",
    )
    resolve_global_edges([api, bean, client])
    assert (
        next(e for _, e in derive_injection_edges([api, bean, client]) if e.type == "INJECTS").meta[
            "target_qualified_name"
        ]
        == "impl.Fast"
    )
    client.entities[0].meta["maven_visibility"] = ["client", "api"]
    assert (
        next(
            e for _, e in derive_injection_edges([api, bean, client]) if e.type == "INJECTS"
        ).resolution
        == "unresolved"
    )


def test_unrelated_annotation_names_are_not_framework_endpoints():
    result = parse(
        'import example.GetMapping; class API { @GetMapping("/fake") public void run() {} }'
    )
    assert not any(e.type == "endpoint" for e in result.entities)
