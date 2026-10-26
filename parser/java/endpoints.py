"""Static HTTP/SOAP endpoint declarations with original Java method evidence."""

from itertools import product

from core.model import Entity, ParsedEdge
from .annotations import matching, namespaced, strings

SPRING = "org.springframework.web.bind.annotation"
REST_PACKAGES = ("jakarta.ws.rs", "javax.ws.rs")
MAPPINGS = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
    "RequestMapping": "*",
}


def _paths(values):
    raw = values.get("path", values.get("value"))
    return [""] if raw is None else strings(raw)


def _join(base, path):
    return "/" + "/".join(part.strip("/") for part in (base, path) if part.strip("/"))


def _declarations(method, owner, result):
    mappings = matching(method, result, namespaced(MAPPINGS, [SPRING]))
    class_mapping = matching(owner, result, {SPRING + ".RequestMapping"}).get("RequestMapping", {})
    for name, values in mappings.items():
        verbs = [MAPPINGS[name]]
        if name == "RequestMapping" and values.get("method"):
            import re

            verbs = re.findall(
                r"(?:RequestMethod\.)?\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|TRACE)\b",
                values["method"],
            )
        if not _paths(class_mapping) or not _paths(values):
            yield {
                "protocol": "http",
                "framework": "spring",
                "path": None,
                "path_expression": values.get("path", values.get("value")),
                "class_path_expression": class_mapping.get("path", class_mapping.get("value")),
                "resolution": "dynamic",
                "http_method": verbs[0] if len(verbs) == 1 else None,
            }
        for base, path, verb in product(_paths(class_mapping), _paths(values), verbs):
            yield {
                "protocol": "http",
                "framework": "spring",
                "path": _join(base, path),
                "http_method": verb,
                "consumes": strings(values.get("consumes", class_mapping.get("consumes"))),
                "produces": strings(values.get("produces", class_mapping.get("produces"))),
            }
    rest = matching(
        method,
        result,
        namespaced(
            ["Path", "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"], REST_PACKAGES
        ),
    )
    base = matching(owner, result, namespaced(["Path"], REST_PACKAGES)).get("Path", {})
    for verb in rest.keys() - {"Path"}:
        for parent, path in product(_paths(base), _paths(rest.get("Path", {}))):
            yield {
                "protocol": "http",
                "framework": "jaxrs",
                "path": _join(parent, path),
                "http_method": verb,
            }
    payload = matching(
        method, result, {"org.springframework.ws.server.endpoint.annotation.PayloadRoot"}
    ).get("PayloadRoot")
    if payload is not None:
        namespace, local = strings(payload.get("namespace")), strings(payload.get("localPart"))
        if namespace and local:
            yield {
                "protocol": "soap",
                "framework": "spring-ws",
                "namespace": namespace[0],
                "operation": local[0],
            }
    service = matching(owner, result, namespaced(["WebService"], ["jakarta.jws", "javax.jws"])).get(
        "WebService"
    )
    operation = matching(
        method, result, namespaced(["WebMethod"], ["jakarta.jws", "javax.jws"])
    ).get("WebMethod", {})
    if (
        service is not None
        and operation.get("exclude") != "true"
        and ("public" in method.meta.get("modifiers", []) or owner.type == "interface")
    ):
        yield {
            "protocol": "soap",
            "framework": "jaxws",
            "operation": next(iter(strings(operation.get("operationName"))), method.name),
            "namespace": next(iter(strings(service.get("targetNamespace"))), None),
            "service_name": next(iter(strings(service.get("serviceName"))), None),
            "port_type": next(
                iter(strings(service.get("name"))),
                owner.name if owner.type == "interface" else None,
            ),
            "endpoint_interface": next(iter(strings(service.get("endpointInterface"))), None),
            "wsdl_location": next(iter(strings(service.get("wsdlLocation"))), None),
        }


def add_endpoints(result):
    types = {e.qualified_name: e for e in result.entities if e.type in {"class", "interface"}}
    for method in list(result.entities):
        owner = types.get(method.parent_qualified_name)
        if method.type != "method" or owner is None:
            continue
        for index, metadata in enumerate(_declarations(method, owner, result)):
            qname = f"{method.qualified_name}@endpoint:{index}"
            parameters = [
                e
                for e in result.entities
                if e.type == "parameter" and e.parent_qualified_name == method.qualified_name
            ]
            entity = Entity(
                "endpoint",
                metadata.get("path") or metadata.get("operation") or method.name,
                method.start_line,
                method.end_line,
                parent_name=method.name,
                qualified_name=qname,
                parent_qualified_name=method.qualified_name,
                meta={
                    **metadata,
                    "language": "java",
                    "module": method.meta.get("module"),
                    "source_set": method.meta.get("source_set"),
                    "return_type": method.meta.get("return_type"),
                    "parameters": [
                        {
                            "name": p.name,
                            "type": p.meta.get("parameter_type"),
                            "annotations": p.meta.get("annotation_details", []),
                        }
                        for p in parameters
                    ],
                },
            )
            result.entities.append(entity)
            if metadata["protocol"] == "soap":
                _schema_edge(result, qname, method, metadata)
            result.edges.append(
                ParsedEdge(
                    "EXPOSES",
                    qname,
                    method.qualified_name,
                    "resolved",
                    method.start_line,
                    method.start_line,
                    meta={
                        "language": "java",
                        "source_qualified_name": qname,
                        "target_qualified_name": method.qualified_name,
                        "target_file_path": result.path,
                        "framework": metadata["framework"],
                    },
                )
            )


def _schema_edge(result, qname, method, metadata):
    namespace, operation = metadata.get("namespace"), metadata.get("operation")
    spring = metadata["framework"] == "spring-ws"
    result.edges.append(
        ParsedEdge(
            "HANDLES_XML_ELEMENT" if spring else "IMPLEMENTS_OPERATION",
            qname,
            operation or method.name,
            "unresolved",
            method.start_line,
            method.start_line,
            meta={
                "language": "java",
                "source_qualified_name": qname,
                "soap_endpoint": True,
                "target_xml_qname": "{" + namespace + "}" + operation
                if namespace is not None and operation
                else None,
                "target_entity_types": ["xsd_element"] if spring else ["wsdl_operation"],
                "target_operation_role": None if spring else "port_type",
                "target_owner_xml_qname": "{" + namespace + "}" + metadata["port_type"]
                if namespace is not None and metadata.get("port_type")
                else None,
            },
        )
    )
