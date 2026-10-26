"""JAXB QName facts used to link Java declarations to checked-in XSDs."""

from core.model import ParsedEdge
from .annotations import matching, namespaced, strings

PACKAGES = ["jakarta.xml.bind.annotation", "javax.xml.bind.annotation"]


def add_jaxb_edges(result):
    owners = {e.qualified_name: e for e in result.entities if e.type == "class"}
    for entity in result.entities:
        annotations = matching(
            entity,
            result,
            namespaced(
                [
                    "XmlType",
                    "XmlRootElement",
                    "XmlElement",
                    "XmlAttribute",
                    "XmlElementRef",
                    "XmlTransient",
                ],
                PACKAGES,
            ),
        )
        if "XmlTransient" in annotations:
            continue
        owner = owners.get(entity.parent_qualified_name)
        if entity.type == "field" and owner is not None and not annotations:
            accessor = matching(owner, result, namespaced(["XmlAccessorType"], PACKAGES)).get(
                "XmlAccessorType", {}
            )
            if accessor.get("value", "").endswith(".FIELD") and not set(
                entity.meta.get("modifiers", [])
            ) & {"static", "transient"}:
                annotations["XmlElement"] = {}
        for annotation, values in annotations.items():
            raw_name = next(iter(strings(values.get("name"))), None)
            name = (
                entity.name
                if annotation in {"XmlElement", "XmlAttribute"}
                else entity.name[:1].lower() + entity.name[1:]
            )
            if raw_name and raw_name != "##default":
                name = raw_name
            elif entity.type == "method" and entity.name.startswith("get") and len(entity.name) > 3:
                name = entity.name[3:4].lower() + entity.name[4:]
            namespace = next(iter(strings(values.get("namespace"))), None)
            if namespace == "##default":
                namespace = None
            targets = {
                "XmlType": ["xsd_complex_type", "xsd_simple_type"],
                "XmlRootElement": ["xsd_element"],
                "XmlElement": ["xsd_element"],
                "XmlAttribute": ["xsd_attribute"],
                "XmlElementRef": ["xsd_element"],
            }[annotation]
            kind = "MAPS_XML_TYPE" if annotation == "XmlType" else "MAPS_XML_ELEMENT"
            owner_type = (
                entity.parent_qualified_name
                if entity.type in {"field", "method"}
                else entity.qualified_name
            )
            package = (
                (owner_type or "").split("#", 1)[0].rsplit(".", 1)[0]
                if "." in (owner_type or "")
                else ""
            )
            result.edges.append(
                ParsedEdge(
                    kind,
                    entity.qualified_name,
                    name,
                    "unresolved",
                    entity.start_line,
                    entity.end_line,
                    meta={
                        "language": "java",
                        "source_qualified_name": entity.qualified_name,
                        "xml_local_name": name,
                        "xml_namespace": namespace,
                        "jaxb_package": package,
                        "jaxb_owner": entity.parent_qualified_name
                        if entity.type in {"field", "method"} and annotation != "XmlElementRef"
                        else None,
                        "target_entity_types": targets,
                        "jaxb_annotation": annotation,
                    },
                )
            )
    root = next((e for e in result.entities if e.meta.get("is_file_root")), None)
    package_entity = next((e for e in result.entities if e.type == "package"), None)
    if root is not None and package_entity is not None:
        schema = matching(package_entity, result, namespaced(["XmlSchema"], PACKAGES)).get(
            "XmlSchema"
        )
        if schema is not None:
            root.meta["jaxb_package"] = package_entity.name
            root.meta["jaxb_package_namespace"] = next(iter(strings(schema.get("namespace"))), "")
            root.meta["jaxb_element_form"] = schema.get("elementFormDefault", "UNQUALIFIED")
