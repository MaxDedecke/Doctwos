"""WSDL 1.1 and XML Schema declarations, QName references and local imports."""

import posixpath
from urllib.parse import urlparse

from core.model import Entity, ParsedEdge
from .xml_facts import qname

WSDL = "http://schemas.xmlsoap.org/wsdl/"
XSD = "http://www.w3.org/2001/XMLSchema"
KINDS = {
    WSDL: {
        "service": "wsdl_service",
        "port": "wsdl_port",
        "binding": "wsdl_binding",
        "portType": "wsdl_port_type",
        "operation": "wsdl_operation",
        "message": "wsdl_message",
        "part": "wsdl_part",
    },
    XSD: {
        "schema": "xsd_schema",
        "complexType": "xsd_complex_type",
        "simpleType": "xsd_simple_type",
        "element": "xsd_element",
        "attribute": "xsd_attribute",
        "group": "xsd_group",
        "attributeGroup": "xsd_attribute_group",
    },
}


def _namespace(fact):
    return fact["tag"].rsplit("}", 1)[0] if "}" in fact["tag"] else ""


def add_schema_xml(result, facts):
    root = result.entities[0]
    by_index, contexts = {}, {}
    for index, fact in enumerate(facts):
        inherited = contexts.get(fact["parent"], {})
        contexts[index] = {**inherited}
        if fact["local"] in {"schema", "definitions"}:
            contexts[index].update(
                namespace=fact["attrs"].get("targetNamespace", ""),
                element_form=fact["attrs"].get("elementFormDefault", "unqualified"),
            )
        context = contexts[index]
        kind = KINDS.get(_namespace(fact), {}).get(fact["local"])
        if kind is None:
            continue
        attrs = fact["attrs"]
        parent = _owner(fact["parent"], facts, by_index) or root
        name = attrs.get("name") or (
            f"anonymous:{index}"
            if fact["local"] != "schema"
            else context.get("namespace") or "schema"
        )
        global_symbol = fact["parent"] is not None and facts[fact["parent"]]["local"] in {
            "schema",
            "definitions",
        }
        namespace = context.get("namespace", "")
        if kind in {"xsd_element", "xsd_attribute"} and not global_symbol:
            form = attrs.get(
                "form", context.get("element_form") if kind == "xsd_element" else "unqualified"
            )
            namespace = namespace if form == "qualified" else ""
        symbol = "{" + namespace + "}" + name
        identity = f"{parent.qualified_name}::{kind}:{symbol}:{index}"
        metadata = {
            "language": "xml",
            "xml_qname": symbol,
            "target_namespace": context.get("namespace", ""),
            "global_symbol": global_symbol,
            "owner_xml_qname": parent.meta.get("xml_qname"),
            "attributes": dict(attrs),
        }
        if kind == "wsdl_operation":
            metadata["operation_role"] = "binding" if parent.type == "wsdl_binding" else "port_type"
        if kind == "wsdl_binding":
            metadata["port_type_qname"] = (
                qname(attrs["type"], fact["namespaces"]) if attrs.get("type") else None
            )
        entity = Entity(
            kind,
            name,
            fact["start_line"],
            fact["end_line"],
            parent_name=parent.name,
            parent_qualified_name=parent.qualified_name,
            qualified_name=identity,
            meta=metadata,
        )
        by_index[index] = entity
        result.entities.append(entity)
    for index, fact in enumerate(facts):
        _references(result, index, fact, facts, contexts, by_index)
    root.meta["target_namespace"] = facts[0]["attrs"].get("targetNamespace", "") if facts else ""


def _owner(index, facts, entities):
    while index is not None:
        if index in entities:
            return entities[index]
        index = facts[index]["parent"]
    return None


def _references(result, index, fact, facts, contexts, entities):
    owner = _owner(index, facts, entities) or result.entities[0]
    attrs, namespace, local = fact["attrs"], _namespace(fact), fact["local"]

    def edge(kind, value, target_types, **extra):
        symbol = qname(value, fact["namespaces"])
        result.edges.append(
            ParsedEdge(
                kind,
                owner.qualified_name,
                symbol or value,
                "unresolved" if symbol else "dynamic",
                fact["start_line"],
                fact["end_line"],
                meta={
                    "language": "xml",
                    "source_qualified_name": owner.qualified_name,
                    "target_xml_qname": symbol,
                    "target_entity_types": target_types,
                    "source_file_path": result.path,
                    **extra,
                },
            )
        )

    if namespace in {WSDL, XSD} and local in {"import", "include", "redefine"}:
        location = attrs.get("schemaLocation", attrs.get("location"))
        target = None
        resolution = "unresolved"
        if location:
            parsed = urlparse(location)
            if parsed.scheme or parsed.netloc:
                resolution = "external"
            elif not location.startswith("/") and "{" not in location:
                candidate = posixpath.normpath(
                    posixpath.join(posixpath.dirname(result.path), location)
                )
                if not candidate.startswith("../"):
                    target = candidate
            else:
                resolution = "dynamic"
        result.edges.append(
            ParsedEdge(
                "INCLUDES",
                owner.qualified_name,
                location or attrs.get("namespace", ""),
                resolution,
                fact["start_line"],
                fact["end_line"],
                meta={
                    "language": "xml",
                    "schema_import": True,
                    "import_kind": local,
                    "source_qualified_name": owner.qualified_name,
                    "target_file_path": target,
                    "import_namespace": attrs.get(
                        "namespace", contexts[index].get("namespace") if local != "import" else None
                    ),
                    "source_file_path": result.path,
                },
            )
        )
    if namespace == WSDL:
        if local == "port" and attrs.get("binding"):
            edge("BINDS_TO", attrs["binding"], ["wsdl_binding"])
        if local == "binding" and attrs.get("type"):
            edge("BINDS_TO", attrs["type"], ["wsdl_port_type"])
        if local in {"input", "output", "fault"} and attrs.get("message"):
            edge(
                {"input": "INPUT_MESSAGE", "output": "OUTPUT_MESSAGE", "fault": "FAULT_MESSAGE"}[
                    local
                ],
                attrs["message"],
                ["wsdl_message"],
            )
        if local == "part":
            for attribute, targets in [
                ("element", ["xsd_element"]),
                ("type", ["xsd_complex_type", "xsd_simple_type"]),
            ]:
                if attrs.get(attribute):
                    edge("USES_XML_TYPE", attrs[attribute], targets)
        if owner.type == "wsdl_operation" and owner.meta.get("operation_role") == "binding":
            parent = next(
                (e for e in result.entities if e.qualified_name == owner.parent_qualified_name),
                None,
            )
            if parent and parent.meta.get("port_type_qname") and local == "operation":
                edge(
                    "IMPLEMENTS_OPERATION",
                    owner.meta["xml_qname"],
                    ["wsdl_operation"],
                    target_owner_xml_qname=parent.meta["port_type_qname"],
                    target_operation_role="port_type",
                )
    if namespace == XSD:
        if attrs.get("type"):
            edge("USES_XML_TYPE", attrs["type"], ["xsd_complex_type", "xsd_simple_type"])
        if local in {"extension", "restriction"} and attrs.get("base"):
            edge("EXTENDS_XML_TYPE", attrs["base"], ["xsd_complex_type", "xsd_simple_type"])
        if attrs.get("ref"):
            edge("REFERENCES_XML_ELEMENT", attrs["ref"], [KINDS[XSD].get(local, "xsd_element")])
    if namespace in {
        "http://schemas.xmlsoap.org/wsdl/soap/",
        "http://schemas.xmlsoap.org/wsdl/soap12/",
    }:
        if local == "address":
            owner.meta["endpoint_address"] = attrs.get("location")
        if local == "operation":
            owner.meta["soap_action"] = attrs.get("soapAction")
