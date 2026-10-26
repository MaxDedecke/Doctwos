"""Resolve source-local Spring XML references without executing the container."""

from java.modules import module_from_path


def resolve_configuration_edges(entities, edges):
    for edge in edges:
        meta = dict(edge.meta_json or {})
        if meta.get("language") != "xml" or edge.type not in {"CONFIGURES", "INJECTS"}:
            continue
        source = next((e for e in entities if e.id == edge.src_entity_id), None)
        if source is None:
            continue
        if edge.type == "CONFIGURES":
            candidates = [
                e
                for e in entities
                if e.type == "class"
                and e.qualified_name == meta.get("requested_java_type")
                and e.variant_key == source.variant_key
            ]
        else:
            candidates = [
                e
                for e in entities
                if e.type == "spring_bean"
                and e.variant_key == source.variant_key
                and meta.get("bean_reference") in (e.meta_json or {}).get("bean_names", [])
            ]
            local = [e for e in candidates if e.file_path == source.file_path]
            if local:
                candidates = local
        module = module_from_path(source.file_path)
        local = [
            e for e in candidates if module is not None and module_from_path(e.file_path) == module
        ]
        if local:
            candidates = local
        edge.dst_entity_id = candidates[0].id if len(candidates) == 1 else None
        edge.resolution = "resolved" if len(candidates) == 1 else "unresolved"
        meta.update(
            candidate_count=len(candidates),
            resolution_reason="configuration_target"
            if len(candidates) == 1
            else "ambiguous_or_missing_configuration_target",
        )
        edge.meta_json = meta
