"""QName-accurate WSDL/XSD/JAXB links, isolated by source and build variant."""

from collections import defaultdict

from doctus_models.database import CodeEdge
from sqlalchemy import or_

from java.modules import module_from_path

SCHEMA_EDGES = {
    "BINDS_TO",
    "INPUT_MESSAGE",
    "OUTPUT_MESSAGE",
    "FAULT_MESSAGE",
    "USES_XML_TYPE",
    "EXTENDS_XML_TYPE",
    "REFERENCES_XML_ELEMENT",
    "IMPLEMENTS_OPERATION",
    "MAPS_XML_TYPE",
    "MAPS_XML_ELEMENT",
    "HANDLES_XML_ELEMENT",
}


def _package_defaults(entities):
    result = {}
    for entity in entities:
        meta = entity.meta_json or {}
        if meta.get("is_file_root") and "jaxb_package_namespace" in meta:
            form = meta.get("jaxb_element_form", "")
            result[
                (entity.variant_key, module_from_path(entity.file_path), meta.get("jaxb_package"))
            ] = (
                meta["jaxb_package_namespace"],
                "QUALIFIED" in form and "UNQUALIFIED" not in form,
            )
    return result


def _jaxb_symbol(meta, source, defaults):
    namespace = meta.get("xml_namespace")
    if namespace is None:
        namespace, qualified = defaults.get(
            (source.variant_key, module_from_path(source.file_path), meta.get("jaxb_package")),
            ("", False),
        )
        if meta.get("jaxb_annotation") in {"XmlElement", "XmlAttribute"} and not qualified:
            namespace = ""
    return "{" + namespace + "}" + meta["xml_local_name"]


def resolve_schema_edges(db, source_id):
    from tasks.edge_resolver import resolution_entity_rows

    edges = (
        db.query(CodeEdge)
        .filter(
            CodeEdge.source_id == source_id,
            or_(
                CodeEdge.type.in_(SCHEMA_EDGES),
                CodeEdge.meta_json["schema_import"].as_string().isnot(None),
            ),
        )
        .all()
    )
    if not edges:
        return 0
    entities = resolution_entity_rows(db, source_id)
    by_id = {e.id: e for e in entities}
    by_xml, roots = defaultdict(list), defaultdict(list)
    for entity in entities:
        meta = entity.meta_json or {}
        if meta.get("xml_qname"):
            by_xml[(entity.variant_key, meta["xml_qname"], entity.type)].append(entity)
        if meta.get("is_file_root"):
            roots[(entity.variant_key, entity.file_path)].append(entity)
    defaults = _package_defaults(entities)
    mappings = {}
    resolved = 0
    for edge in sorted(edges, key=lambda e: e.type != "MAPS_XML_TYPE"):
        meta = dict(edge.meta_json or {})
        if meta.get("schema_import"):
            if edge.resolution in {"external", "dynamic"} and not meta.get("target_file_path"):
                continue
            matches = roots.get((edge.variant_key, meta.get("target_file_path")), [])
            expected = meta.get("import_namespace")
            if expected is not None:
                allowed = {expected, ""} if meta.get("import_kind") != "import" else {expected}
                matches = [
                    e for e in matches if (e.meta_json or {}).get("target_namespace", "") in allowed
                ]
            _assign(edge, matches, meta)
            resolved += int(edge.resolution == "resolved")
            continue
        if edge.type not in SCHEMA_EDGES:
            continue
        source = by_id.get(edge.src_entity_id)
        if source is None:
            continue
        symbol = meta.get("target_xml_qname")
        if meta.get("soap_endpoint") and not symbol:
            symbol, inherited = _inherited_soap_symbol(source, entities, by_id)
            if inherited:
                meta["schema_annotation_source"] = inherited
        if meta.get("xml_local_name"):
            symbol = _jaxb_symbol(meta, source, defaults)
        meta["effective_xml_qname"] = symbol
        if symbol and symbol.startswith("{http://www.w3.org/2001/XMLSchema}"):
            edge.dst_entity_id = None
            edge.resolution = "external"
            edge.meta_json = {
                **meta,
                "external": {"category": "xsd_builtin", "qualified_name": symbol},
            }
            continue
        matches = (
            [
                entity
                for kind in meta.get("target_entity_types", [])
                for entity in by_xml.get((edge.variant_key, symbol, kind), [])
            ]
            if symbol
            else []
        )
        owner = meta.get("target_owner_xml_qname")
        if owner:
            matches = [e for e in matches if (e.meta_json or {}).get("owner_xml_qname") == owner]
        if meta.get("target_operation_role"):
            matches = [
                e
                for e in matches
                if (e.meta_json or {}).get("operation_role") == meta["target_operation_role"]
            ]
        if edge.type in {
            "BINDS_TO",
            "INPUT_MESSAGE",
            "OUTPUT_MESSAGE",
            "FAULT_MESSAGE",
            "USES_XML_TYPE",
            "EXTENDS_XML_TYPE",
            "REFERENCES_XML_ELEMENT",
        }:
            matches = [e for e in matches if (e.meta_json or {}).get("global_symbol")]
        jaxb_owner = meta.get("jaxb_owner")
        if jaxb_owner:
            owner_symbol = mappings.get((edge.variant_key, source.file_path, jaxb_owner))
            matches = [
                e
                for e in matches
                if owner_symbol is not None
                and (e.meta_json or {}).get("owner_xml_qname") == owner_symbol
            ]
        elif edge.type in {"MAPS_XML_TYPE", "MAPS_XML_ELEMENT", "HANDLES_XML_ELEMENT"}:
            matches = [e for e in matches if (e.meta_json or {}).get("global_symbol")]
        _assign(edge, matches, meta)
        if edge.resolution == "resolved":
            resolved += 1
            if edge.type == "MAPS_XML_TYPE":
                mappings[(edge.variant_key, source.file_path, source.qualified_name)] = symbol
    return resolved


def _assign(edge, matches, meta):
    edge.dst_entity_id = matches[0].id if len(matches) == 1 else None
    edge.resolution = "resolved" if len(matches) == 1 else "unresolved"
    meta.update(
        candidate_count=len(matches),
        resolution_reason="schema_qname"
        if len(matches) == 1
        else ("ambiguous_schema" if matches else "schema_not_found"),
    )
    if len(matches) == 1:
        meta.update(
            target_qualified_name=matches[0].qualified_name, target_file_path=matches[0].file_path
        )
    else:
        meta.pop("target_qualified_name", None)
        if not meta.get("schema_import"):
            meta.pop("target_file_path", None)
    edge.meta_json = meta


def _inherited_soap_symbol(source, entities, by_id):
    meta = source.meta_json or {}
    interface = meta.get("endpoint_interface")
    matches = [
        e
        for e in entities
        if e.variant_key == source.variant_key
        and e.type == "endpoint"
        and (e.meta_json or {}).get("namespace") is not None
        and (e.meta_json or {}).get("operation") == meta.get("operation")
        and e.parent_id in by_id
        and (by_id[e.parent_id].qualified_name or "").startswith((interface or "\0") + "#")
    ]
    if len(matches) == 1:
        target = matches[0]
        return "{" + target.meta_json["namespace"] + "}" + target.meta_json[
            "operation"
        ], target.qualified_name
    return None, None
