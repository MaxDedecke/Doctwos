"""Recompute framework-derived edges after normal Java symbol resolution."""

from collections import defaultdict

from java.injection import derive_injection_edges
from java.modules import module_from_path
from core.model import Entity, ParseResult
from models.database import CodeEntity, CodeEdge
from tasks.configuration_resolver import resolve_configuration_edges


def resolve_framework_edges(db, source_id):
    from tasks.edge_resolver import _java_parse_results

    entities = db.query(CodeEntity).filter(CodeEntity.source_id == source_id).all()
    edges = db.query(CodeEdge).filter(CodeEdge.source_id == source_id).all()
    resolve_configuration_edges(entities, edges)
    for edge in edges:
        if (edge.meta_json or {}).get("derivation") == "framework":
            db.delete(edge)
    groups = defaultdict(list)
    for result, _, _ in _java_parse_results(entities, edges):
        groups[result.variant_key].append(result)
    by_identity = {(e.variant_key, e.file_path, e.qualified_name): e for e in entities}
    resolved = 0
    for variant, results in groups.items():
        xml_beans = []
        for row in entities:
            if row.type == "spring_bean" and row.variant_key == variant:
                bean = Entity(
                    row.type,
                    row.name,
                    row.start_line,
                    row.end_line,
                    qualified_name=row.qualified_name,
                    meta={
                        **(row.meta_json or {}),
                        "module": module_from_path(row.file_path),
                        "source_set": "main",
                    },
                )
                xml_beans.append(
                    (ParseResult(row.name, row.file_path, "free", variant_key=variant), bean)
                )
        for result, edge in derive_injection_edges(results, xml_beans):
            source = by_identity.get((variant, result.path, edge.src_name))
            target = by_identity.get(
                (variant, edge.meta.get("target_file_path"), edge.meta.get("target_qualified_name"))
            )
            if source is None:
                continue
            db.add(
                CodeEdge(
                    project_id=source.project_id,
                    source_id=source_id,
                    variant_key=variant,
                    src_entity_id=source.id,
                    dst_entity_id=target.id if target else None,
                    type=edge.type,
                    dst_name=edge.dst_name,
                    resolution="resolved" if target else "unresolved",
                    src_start_line=edge.src_start_line,
                    src_end_line=edge.src_end_line,
                    meta_json=edge.meta,
                )
            )
            resolved += int(target is not None)
    db.flush()
    return resolved
