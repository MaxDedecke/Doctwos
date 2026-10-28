"""Project boundaries for legacy links whose ownership lives on their endpoints."""

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select

from core.projects import assert_project_visible
from doctus_models.database import (
    CodeEntity,
    DocumentChunk,
    KnowledgeLink,
    KnowledgeSource,
    Project,
)


def assert_link_project(project_id, user, db):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)


def side_in_project(side, project_id):
    entity_id = getattr(KnowledgeLink, f"source_{side}_entity_id")
    chunk_id = getattr(KnowledgeLink, f"source_{side}_chunk_id")
    entity_type = getattr(KnowledgeLink, f"source_{side}_type")
    entity = (
        select(CodeEntity.id)
        .outerjoin(KnowledgeSource, KnowledgeSource.id == CodeEntity.source_id)
        .where(
            CodeEntity.id == entity_id,
            func.coalesce(CodeEntity.project_id, KnowledgeSource.project_id) == project_id,
        )
        .exists()
    )
    chunk = (
        select(DocumentChunk.id)
        .outerjoin(KnowledgeSource, KnowledgeSource.id == DocumentChunk.source_id)
        .where(
            DocumentChunk.id == chunk_id,
            func.coalesce(DocumentChunk.project_id, KnowledgeSource.project_id) == project_id,
        )
        .exists()
    )
    return or_(
        and_(entity_type == "entity", entity_id.isnot(None), entity),
        and_(or_(entity_type == "document", entity_id.is_(None)), chunk),
    )


def filter_project_links(query, project_id):
    if project_id is None:
        return query
    # Both ends must belong to the project. Unknown/manual legacy origins and
    # old cross-project links must never leak into a newly selected project.
    return query.filter(
        or_(
            KnowledgeLink.project_id == project_id,
            and_(
                KnowledgeLink.project_id.is_(None),
                side_in_project("a", project_id),
                side_in_project("b", project_id),
            ),
        )
    )


def assert_link_sides_in_project(link, project_id, db):
    for side in ("a", "b"):
        entity_id = getattr(link, f"source_{side}_entity_id")
        chunk_id = getattr(link, f"source_{side}_chunk_id")
        if entity_id is None and chunk_id is None:
            continue
        if getattr(link, f"source_{side}_type") == "entity" and entity_id is not None:
            row = db.get(CodeEntity, entity_id)
        else:
            row = db.get(DocumentChunk, chunk_id) if chunk_id is not None else None
        owner = row.project_id if row is not None else None
        if row is not None and owner is None and row.source_id:
            source = db.get(KnowledgeSource, row.source_id)
            owner = source.project_id if source else None
        if owner != project_id:
            raise HTTPException(
                status_code=422, detail="Beide Link-Seiten müssen zum Projekt gehören"
            )
