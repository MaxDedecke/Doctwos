"""Recompute framework-derived edges after normal Java symbol resolution."""

from collections import defaultdict

from doctus_models.database import CodeEdge, CodeEntity
from sqlalchemy import or_

from core.model import Entity, ParseResult
from java.injection import derive_injection_edges
from java.lambda_dispatch import derive_lambda_dispatch
from java.modules import module_from_path
from tasks.configuration_resolver import resolve_configuration_edges
from tasks.resolver_rows import load_entity_rows


def _resolve_configuration(db, source_id):
    from tasks.edge_resolver import UNREAD_JAVA_ENTITY_META

    edges = (
        db.query(CodeEdge)
        .filter(
            CodeEdge.source_id == source_id,
            CodeEdge.type.in_(("CONFIGURES", "INJECTS")),
            CodeEdge.meta_json["language"].as_string() == "xml",
        )
        .all()
    )
    if not edges:
        return
    sources = {edge.src_entity_id for edge in edges}
    entities = load_entity_rows(
        db,
        CodeEntity.source_id == source_id,
        or_(CodeEntity.type.in_(("class", "spring_bean")), CodeEntity.id.in_(sources)),
        drop=UNREAD_JAVA_ENTITY_META,
    )
    resolve_configuration_edges(entities, edges)
    db.flush()


def resolve_framework_edges(db, source_id):
    from tasks.edge_resolver import (
        UNREAD_FRAMEWORK_ENTITY_META,
        UNREAD_JAVA_ENTITY_META,
        _java_parse_results,
        java_edge_rows,
        java_entity_rows,
    )

    _resolve_configuration(db, source_id)
    db.query(CodeEdge).filter(
        CodeEdge.source_id == source_id,
        CodeEdge.meta_json["derivation"].as_string().in_(("framework", "lambda_binding")),
    ).delete(synchronize_session=False)
    db.expire_all()
    language = CodeEntity.meta_json["language"].as_string()
    entities = java_entity_rows(db, source_id, UNREAD_FRAMEWORK_ENTITY_META)
    entities += load_entity_rows(
        db,
        CodeEntity.source_id == source_id,
        CodeEntity.type == "spring_bean",
        or_(language != "java", language.is_(None)),
        drop=UNREAD_JAVA_ENTITY_META,
    )
    edges = java_edge_rows(db, source_id)
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
        derived = list(derive_injection_edges(results, xml_beans)) + list(
            derive_lambda_dispatch(results)
        )
        for result, edge in derived:
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
