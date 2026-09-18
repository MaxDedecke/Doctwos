"""Source-backed resource links across language boundaries; never basename joins."""

import posixpath
from collections import defaultdict

from java.modules import module_from_path
from core.evidence import source_evidence


RESOURCE_EDGE_TYPES = frozenset({
    "USES_RESOURCE", "INCLUDES", "IMPORTS", "TRANSFORMS_WITH", "READS_XML",
    "SOURCES", "EXECUTES_SCRIPT", "STARTS_JAVA", "REFERENCES_RESOURCE", "LINKS_TO",
})


def resolve_resource_edges(entities, edges):
    """Refresh persisted links, including formerly resolved and now missing targets."""
    by_id = {entity.id: entity for entity in entities}
    by_path, by_qname = defaultdict(list), defaultdict(list)
    entrypoints = defaultdict(list)
    for entity in entities:
        by_path[(entity.variant_key, entity.file_path)].append(entity)
        by_qname[(entity.variant_key, entity.qualified_name)].append(entity)
        entity_meta = entity.meta_json or {}
        if (entity.type == "method" and entity.qualified_name
                and "#main(" in entity.qualified_name
                and {"public", "static"} <= set(entity_meta.get("modifiers", []))
                and entity_meta.get("return_type") == "void"
                and entity_meta.get("parameter_types") in (["String[]"], ["java.lang.String[]"])):
            entrypoints[(entity.variant_key, entity.file_path,
                         entity.qualified_name.split("#", 1)[0])].append(entity)
    resolved = 0
    for edge in edges:
        meta = dict(edge.meta_json or {})
        if edge.type not in RESOURCE_EDGE_TYPES or meta.get("language") not in {
            "java", "shell", "xslt", "jsp", "html"
        }:
            continue
        if edge.type == "IMPORTS" and meta.get("language") != "xslt":
            continue
        source = by_id.get(edge.src_entity_id)
        if source is None:
            continue
        target = meta.get("target_file_path")
        qname = meta.get("target_qualified_name") if edge.type == "STARTS_JAVA" else None
        module = module_from_path(source.file_path)
        paths = {target} if target else set()
        if meta.get("resource_base") == "classpath" and target:
            # No classpath ordering or dependency guessing: only this module's
            # conventional resource root is justified by the source path.
            paths = set()
            if module is not None:
                source_set = (source.meta_json or {}).get("source_set", "main")
                root = posixpath.normpath(f"{module}/src/{source_set}/resources")
                candidate = posixpath.normpath(f"{root}/{target}")
                if candidate.startswith(root + "/"):
                    paths.add(candidate)
        candidates = []
        pool = {entity.id: entity for path in paths
                for entity in by_path[(edge.variant_key, path)]}
        if qname:
            pool.update({entity.id: entity for entity in by_qname[(edge.variant_key, qname)]
                         if entity.type in {"class", "enum", "record"}})
        for entity in pool.values():
            target_type = meta.get("target_entity_type")
            if target_type and entity.type != target_type:
                continue
            if not target_type and not qname and not (entity.meta_json or {}).get("is_file_root"):
                continue
            if qname and module is not None and module_from_path(entity.file_path) != module:
                continue
            candidates.append(entity)
        was_resolved = edge.resolution == "resolved"
        edge.dst_entity_id = None
        if edge.resolution == "dynamic":
            reason = "dynamic_resource_expression"
        elif len(candidates) == 1:
            target_entity = candidates[0]
            if qname:
                mains = entrypoints[(edge.variant_key, target_entity.file_path, qname)]
                if len(mains) == 1:
                    target_entity = mains[0]
            edge.dst_entity_id = target_entity.id
            edge.resolution = "resolved"
            reason = "exact_resource_target"
            resolved += not was_resolved
        else:
            edge.resolution = "unresolved"
            reason = "ambiguous_resource_target" if candidates else "resource_target_not_found"
        meta.update(resolution_reason=reason, candidate_count=len(candidates),
                    source_file_path=source.file_path, relationship_kind="resource")
        meta.setdefault("evidence", source_evidence(
            path=source.file_path, start_line=edge.src_start_line,
            end_line=getattr(edge, "src_end_line", edge.src_start_line), profile=None,
        ))
        meta["evidence"]["variant"]["key"] = edge.variant_key
        edge.meta_json = meta
    return resolved
