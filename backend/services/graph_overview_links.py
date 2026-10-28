"""Bulk-load knowledge-link endpoints without vectors, source text or per-edge queries."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import load_only

from doctus_models.database import (
    CodeEntity,
    DocumentChunk,
    KnowledgeLink,
    KnowledgeSource,
    Project,
)


def _scope_side(side, project_id):
    entity_id = getattr(KnowledgeLink, f"source_{side}_entity_id")
    chunk_id = getattr(KnowledgeLink, f"source_{side}_chunk_id")
    kind = getattr(KnowledgeLink, f"source_{side}_type")
    entity_scope = CodeEntity.project_id.is_(None)
    if project_id is not None:
        entity_scope = or_(entity_scope, CodeEntity.project_id == project_id)
    # Global code visibility is checked against the preloaded project map below.
    entity = select(CodeEntity.id).where(CodeEntity.id == entity_id)
    if project_id is not None:
        entity = entity.where(entity_scope)
    chunk_scope = DocumentChunk.project_id.is_(None)
    if project_id is not None:
        chunk_scope = or_(chunk_scope, DocumentChunk.project_id == project_id)
    chunk = select(DocumentChunk.id).where(DocumentChunk.id == chunk_id, chunk_scope)
    return or_(
        and_(kind == "entity", entity_id.isnot(None), entity.exists()),
        and_(or_(kind != "entity", entity_id.is_(None)), or_(chunk_id.is_(None), chunk.exists())),
    )


def _load_link_endpoints(db, links):
    entity_ids = {
        getattr(link, f"source_{side}_entity_id")
        for link in links
        for side in ("a", "b")
        if getattr(link, f"source_{side}_type") == "entity"
        and getattr(link, f"source_{side}_entity_id") is not None
    }
    chunk_ids = {
        getattr(link, f"source_{side}_chunk_id")
        for link in links
        for side in ("a", "b")
        if getattr(link, f"source_{side}_chunk_id") is not None
    }
    entities = (
        {
            row.id: row
            for row in db.query(CodeEntity)
            .options(
                load_only(
                    CodeEntity.id,
                    CodeEntity.project_id,
                    CodeEntity.source_id,
                    CodeEntity.file_path,
                    CodeEntity.meta_json,
                    CodeEntity.name,
                    CodeEntity.type,
                    CodeEntity.start_line,
                )
            )
            .filter(CodeEntity.id.in_(entity_ids))
            .all()
        }
        if entity_ids
        else {}
    )
    chunks = (
        {
            row.id: row
            for row in db.query(DocumentChunk)
            .options(
                load_only(
                    DocumentChunk.id,
                    DocumentChunk.project_id,
                    DocumentChunk.source_id,
                    DocumentChunk.file_path,
                    DocumentChunk.metadata_json,
                )
            )
            .filter(DocumentChunk.id.in_(chunk_ids))
            .all()
        }
        if chunk_ids
        else {}
    )
    all_endpoints = [*entities.values(), *chunks.values()]
    source_ids = {row.source_id for row in all_endpoints if row.source_id is not None}
    sources = (
        {
            row.id: row
            for row in db.query(KnowledgeSource)
            .options(
                load_only(
                    KnowledgeSource.id,
                    KnowledgeSource.team_id,
                    KnowledgeSource.project_id,
                    KnowledgeSource.type,
                )
            )
            .filter(KnowledgeSource.id.in_(source_ids))
            .all()
        }
        if source_ids
        else {}
    )
    endpoint_project_ids = {row.project_id for row in all_endpoints if row.project_id is not None}
    projects = (
        {
            row.id: row
            for row in db.query(Project)
            .options(
                load_only(
                    Project.id,
                    Project.team_id,
                    Project.expose_code_analysis_globally,
                )
            )
            .filter(Project.id.in_(endpoint_project_ids))
            .all()
        }
        if endpoint_project_ids
        else {}
    )
    return entities, chunks, sources, projects


def append_overview_knowledge_links(
    nodes,
    edges,
    preserved,
    db,
    status,
    project_id,
    team_ids,
    project_ids,
    ensure_file_node,
    document_node,
):
    links = (
        db.query(KnowledgeLink)
        .filter(
            KnowledgeLink.status == status,
            _scope_side("a", project_id),
            _scope_side("b", project_id),
        )
        .order_by(KnowledgeLink.id)
        .all()
    )
    if not links:
        return
    entities, chunks, sources, projects = _load_link_endpoints(db, links)
    teams = set(team_ids) if team_ids is not None else None
    visible_projects = set(project_ids or [])

    def visible(row, is_entity):
        if row is None:
            return False
        pid, sid = row.project_id, row.source_id
        if pid is not None and pid != project_id and (project_id is not None or not is_entity):
            return False
        project = projects.get(pid)
        source = sources.get(sid)
        if teams is not None:
            if pid is not None and (
                not project or project.team_id not in teams or pid not in visible_projects
            ):
                return False
            if sid is not None and (
                not source
                or source.team_id not in teams
                or (source.project_id is not None and source.project_id not in visible_projects)
            ):
                return False
        if is_entity or (source and source.type == "Git"):
            if (
                pid is not None
                and pid != project_id
                and not (project and project.expose_code_analysis_globally)
            ):
                return False
        return True

    def side_node(link, side):
        kind = getattr(link, f"source_{side}_type")
        entity_id = getattr(link, f"source_{side}_entity_id")
        chunk_id = getattr(link, f"source_{side}_chunk_id")
        if kind == "entity" and entity_id is not None:
            entity = entities.get(entity_id)
            return ensure_file_node(nodes, entity) if visible(entity, True) else None
        chunk = chunks.get(chunk_id)
        if chunk_id is not None and not visible(chunk, False):
            return None
        node = document_node(
            getattr(link, f"source_{side}_title"),
            getattr(link, f"source_{side}_source_type"),
            getattr(link, f"source_{side}_url"),
            chunk,
        )
        nodes.setdefault(node["id"], node)
        return node["id"]

    for link in links:
        # Don't leave an isolated first endpoint behind when its peer is invisible.
        endpoints = []
        for side in ("a", "b"):
            entity_id = getattr(link, f"source_{side}_entity_id")
            chunk_id = getattr(link, f"source_{side}_chunk_id")
            is_entity = getattr(link, f"source_{side}_type") == "entity" and entity_id is not None
            row = entities.get(entity_id) if is_entity else chunks.get(chunk_id)
            endpoints.append((entity_id is None and chunk_id is None) or visible(row, is_entity))
        if not all(endpoints):
            continue
        source, target = side_node(link, "a"), side_node(link, "b")
        if source is None or target is None:
            continue
        preserved.update((source, target))
        edges.append(
            {
                "id": f"kl:{link.id}",
                "source": source,
                "target": target,
                "link_type": link.link_type,
                "direction": link.direction or "undirected",
                "score": link.score,
                "context": link.context,
            }
        )
