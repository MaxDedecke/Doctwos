"""Bounded, read-only impact analysis over persisted code relationships."""

from __future__ import annotations

from pathlib import PurePosixPath

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from core.analysis_status import load_analysis_status
from models.database import CodeEdge, CodeEntity, KnowledgeLink


MAX_IMPACT_HOPS = 3
MAX_IMPACT_NODES = 80
MAX_FILE_TARGETS = 20
MAX_HEURISTIC_LINKS = 30


def _entity_json(entity: CodeEntity) -> dict:
    return {
        "id": entity.id,
        "name": entity.name,
        "qualified_name": entity.qualified_name,
        "type": entity.type,
        "file_path": entity.file_path,
        "source_id": entity.source_id,
        "start_line": entity.start_line,
        "end_line": entity.end_line,
    }


def _relative_path(value: str) -> str | None:
    raw = value.replace("\\", "/").strip()
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ".." in path.parts or path.as_posix() == ".":
        return None
    return path.as_posix()


def inspect_change_impact(
    db: Session,
    *,
    project_id: int,
    entity_id: int | None = None,
    file_path: str | None = None,
    source_id: int | None = None,
    direction: str = "incoming",
    hops: int = 2,
    limit: int = 40,
) -> dict:
    """Find bounded dependencies around one entity or one indexed project file.

    ``incoming`` follows edges into the selected entity: their source entities
    depend on it and may therefore be affected by a change. ``outgoing`` shows
    dependencies used by the selected entity. Every returned edge is scoped to
    the current project; approved semantic links are returned separately and
    never presented as statically verified code dependencies.
    """
    if entity_id is None and file_path is None:
        return {"error": "Provide entity_id, file_path, or both for the same indexed file."}
    if source_id is not None and (not isinstance(source_id, int) or isinstance(source_id, bool) or source_id <= 0):
        return {"error": "source_id must be a positive integer."}
    if entity_id is not None and (
        not isinstance(entity_id, int) or isinstance(entity_id, bool) or entity_id <= 0
    ):
        return {"error": "entity_id must be a positive integer."}
    if direction not in {"incoming", "outgoing", "both"}:
        return {"error": "direction must be incoming, outgoing, or both."}
    if not isinstance(hops, int) or isinstance(hops, bool):
        return {"error": "hops must be an integer."}
    if not isinstance(limit, int) or isinstance(limit, bool):
        return {"error": "limit must be an integer."}
    hops = max(0, min(hops, MAX_IMPACT_HOPS))
    limit = max(10, min(limit, MAX_IMPACT_NODES))

    target_kind: str
    normalized_path: str | None = None
    if file_path is not None:
        normalized_path = _relative_path(str(file_path or ""))
        if normalized_path is None:
            return {"error": "file_path must be a safe repository-relative path."}
        if entity_id is not None:
            matching_query = (
                db.query(CodeEntity.id).filter(
                    CodeEntity.id == entity_id,
                    CodeEntity.project_id == project_id,
                    CodeEntity.file_path == normalized_path,
                )
            )
            if source_id is not None:
                matching_query = matching_query.filter(CodeEntity.source_id == source_id)
            matching_entity = matching_query.first()
            if matching_entity is None:
                return {"error": "When both selectors are provided, entity_id must belong to file_path in the current project."}
        file_query = (
            db.query(CodeEntity).filter(
                CodeEntity.project_id == project_id,
                CodeEntity.file_path == normalized_path,
            )
        )
        if source_id is not None:
            file_query = file_query.filter(CodeEntity.source_id == source_id)
        file_entities = file_query.order_by(CodeEntity.start_line, CodeEntity.id).limit(MAX_IMPACT_NODES + 1).all()
        if not file_entities:
            return {"error": "No indexed code entities were found for this file in the current project."}
        file_root = next(
            (entity for entity in file_entities if (entity.meta_json or {}).get("is_file_root")),
            None,
        )
        target_entities = file_entities[: min(MAX_FILE_TARGETS, limit)]
        if file_root and file_root.id not in {entity.id for entity in target_entities}:
            target_entities[-1] = file_root
        target_kind = "file"
        target_count_truncated = len(file_entities) > len(target_entities)
    else:
        target_query = db.query(CodeEntity).filter(CodeEntity.id == entity_id, CodeEntity.project_id == project_id)
        if source_id is not None:
            target_query = target_query.filter(CodeEntity.source_id == source_id)
        target = target_query.first()
        if target is None:
            return {"error": "Entity was not found in the current project."}
        target_entities = [target]
        target_kind = "entity"
        target_count_truncated = False

    seen_ids = {entity.id for entity in target_entities}
    frontier = set(seen_ids)
    edge_rows: dict[int, CodeEdge] = {}
    truncated = target_count_truncated

    for _ in range(hops):
        if not frontier:
            break
        predicates = []
        if direction in {"incoming", "both"}:
            predicates.append(CodeEdge.dst_entity_id.in_(frontier))
        if direction in {"outgoing", "both"}:
            predicates.append(CodeEdge.src_entity_id.in_(frontier))
        rows = (
            db.query(CodeEdge)
            .filter(CodeEdge.project_id == project_id, or_(*predicates))
            .order_by(CodeEdge.id)
            .limit(limit + 1)
            .all()
        )
        if len(rows) > limit:
            truncated = True
            rows = rows[:limit]

        endpoint_ids = {
            endpoint_id
            for edge in rows
            for endpoint_id in (edge.src_entity_id, edge.dst_entity_id)
            if endpoint_id is not None
        }
        valid_endpoint_ids = {
            row_id
            for (row_id,) in db.query(CodeEntity.id).filter(
                CodeEntity.id.in_(endpoint_ids), CodeEntity.project_id == project_id
            )
        } if endpoint_ids else set()

        next_frontier: set[int] = set()
        for edge in rows:
            if edge.src_entity_id not in valid_endpoint_ids:
                continue
            if edge.dst_entity_id is not None and edge.dst_entity_id not in valid_endpoint_ids:
                continue
            edge_rows[edge.id] = edge
            for endpoint_id in (edge.src_entity_id, edge.dst_entity_id):
                if endpoint_id is None or endpoint_id in seen_ids:
                    continue
                if len(seen_ids) >= limit:
                    truncated = True
                    continue
                seen_ids.add(endpoint_id)
                next_frontier.add(endpoint_id)
        frontier = next_frontier

    # Literal unresolved/dynamic references to a selected symbol are useful
    # leads, but name matching is only a candidate and must remain uncertain.
    target_names = {
        name.casefold()
        for entity in target_entities
        for name in (entity.name, entity.qualified_name)
        if isinstance(name, str) and name.strip()
    }
    unknown_matches: list[CodeEdge] = []
    if target_names:
        unknown_matches = (
            db.query(CodeEdge)
            .filter(
                CodeEdge.project_id == project_id,
                CodeEdge.dst_entity_id.is_(None),
                CodeEdge.resolution.in_(("unresolved", "dynamic")),
                func.lower(CodeEdge.dst_name).in_(target_names),
            )
            .order_by(CodeEdge.id)
            .limit(limit + 1)
            .all()
        )
        if len(unknown_matches) > limit:
            truncated = True
            unknown_matches = unknown_matches[:limit]
        for edge in unknown_matches:
            source = (
                db.query(CodeEntity)
                .filter(CodeEntity.id == edge.src_entity_id, CodeEntity.project_id == project_id)
                .first()
            )
            if source is None:
                continue
            if source.id not in seen_ids and len(seen_ids) < limit:
                seen_ids.add(source.id)
            elif source.id not in seen_ids:
                truncated = True
                continue
            edge_rows[edge.id] = edge

    entities = (
        db.query(CodeEntity)
        .filter(CodeEntity.id.in_(seen_ids), CodeEntity.project_id == project_id)
        .order_by(CodeEntity.id)
        .all()
    )
    nodes = [_entity_json(entity) for entity in entities]
    status_by_key = load_analysis_status(
        db, {(entity.source_id, entity.file_path) for entity in entities}
    )
    for node in nodes:
        status = status_by_key.get((node.get("source_id"), node.get("file_path")))
        if status:
            node["analysis_status"] = status["status"]
            node["analysis_reasons"] = status["reasons"]
    nodes_by_id = {node["id"]: node for node in nodes}

    graph_edges = []
    for edge in sorted(edge_rows.values(), key=lambda item: item.id):
        if edge.src_entity_id not in nodes_by_id:
            continue
        if edge.dst_entity_id is not None and edge.dst_entity_id not in nodes_by_id:
            continue
        graph_edges.append({
            "id": edge.id,
            "source": edge.src_entity_id,
            "target": edge.dst_entity_id,
            "target_name": (
                nodes_by_id[edge.dst_entity_id]["name"]
                if edge.dst_entity_id is not None
                else edge.dst_name
            ),
            "type": edge.type,
            "resolution": edge.resolution,
            "meta": edge.meta_json or {},
            "start_line": edge.src_start_line,
            "end_line": edge.src_end_line,
        })
    if len(graph_edges) > limit:
        truncated = True
        graph_edges = graph_edges[:limit]

    # Approved entity-to-entity knowledge links are useful navigation leads,
    # but semantic similarity does not establish a runtime/code dependency.
    candidate_links = (
        db.query(KnowledgeLink)
        .filter(
            KnowledgeLink.status == "approved",
            KnowledgeLink.source_a_type == "entity",
            KnowledgeLink.source_b_type == "entity",
            or_(
                KnowledgeLink.source_a_entity_id.in_(seen_ids),
                KnowledgeLink.source_b_entity_id.in_(seen_ids),
            ),
        )
        .order_by(KnowledgeLink.id)
        .limit(MAX_HEURISTIC_LINKS + 1)
        .all()
    ) if seen_ids else []
    if len(candidate_links) > MAX_HEURISTIC_LINKS:
        truncated = True
        candidate_links = candidate_links[:MAX_HEURISTIC_LINKS]
    related_ids = {
        entity_id
        for link in candidate_links
        for entity_id in (link.source_a_entity_id, link.source_b_entity_id)
        if entity_id is not None
    }
    related_entities = {
        entity.id: entity
        for entity in (
            db.query(CodeEntity)
            .filter(CodeEntity.id.in_(related_ids), CodeEntity.project_id == project_id)
            .all()
            if related_ids else []
        )
    }
    heuristic_links = []
    for link in candidate_links:
        source = related_entities.get(link.source_a_entity_id)
        target = related_entities.get(link.source_b_entity_id)
        if source is None or target is None:
            continue
        heuristic_links.append({
            "id": link.id,
            "source": _entity_json(source),
            "target": _entity_json(target),
            "link_type": link.link_type,
            "direction": link.direction,
            "score": link.score,
            "context": (link.context or "")[:500],
            "reviewed": link.reviewed_at is not None or link.created_by == "user",
        })

    unknown_edges = [
        {
            "id": edge["id"],
            "source_entity_id": edge["source"],
            "source_name": nodes_by_id[edge["source"]]["name"],
            "file_path": nodes_by_id[edge["source"]].get("file_path"),
            "start_line": edge["start_line"],
            "target_name": edge["target_name"],
            "resolution": edge["resolution"],
            "type": edge["type"],
        }
        for edge in graph_edges
        if edge["resolution"] in {"unresolved", "dynamic"}
    ]
    statically_resolved_count = sum(edge["resolution"] == "resolved" for edge in graph_edges)
    heuristic_edge_count = sum(edge["resolution"] == "heuristic" for edge in graph_edges)
    unknown_edge_count = len(unknown_edges)

    target_ids = {entity.id for entity in target_entities}
    root_entity = next(
        (
            entity
            for entity in target_entities
            if any(
                edge["source"] == entity.id or edge["target"] == entity.id
                for edge in graph_edges
            )
        ),
        target_entities[0],
    )
    limitations = [
        "This is a bounded static index query; it does not prove the complete runtime impact.",
        "Reflection, dynamic dispatch, generated code, and unindexed dependencies may be missing.",
    ]
    if truncated:
        limitations.append("The result was truncated by the configured hop, node, or relationship limit.")
    partial_files = sorted({
        node["file_path"]
        for node in nodes
        if node.get("analysis_status") in {"partial", "text_fallback", "error", "skipped"}
    })
    if partial_files:
        limitations.append("Some files have incomplete or unavailable structural analysis: " + ", ".join(partial_files[:8]))

    has_result = bool(graph_edges or heuristic_links)
    return {
        "status": "ok" if has_result else "no_indexed_impact",
        "root": nodes_by_id.get(root_entity.id, _entity_json(root_entity)),
        "hops": hops,
        "direction": direction,
        "truncated": truncated,
        "nodes": nodes,
        "edges": graph_edges,
        "target": {
            "kind": target_kind,
            "file_path": normalized_path,
            "entity_ids": sorted(target_ids),
            "entity_names": [entity.qualified_name or entity.name for entity in target_entities[:12]],
        },
        "impact_summary": {
            "statically_resolved_edges": statically_resolved_count,
            "heuristic_links": len(heuristic_links) + heuristic_edge_count,
            "unknown_dynamic_edges": unknown_edge_count,
            "truncated": truncated,
            "limitations": limitations,
        },
        "heuristic_links": heuristic_links,
        "unknown_edges": unknown_edges[:limit],
    }
