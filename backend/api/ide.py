"""Bounded source annotations for local IDE clients (O-325)."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from core.db_setup import get_db
from core.projects import assert_knowledge_source_visible, assert_project_visible
from models.database import CodeEdge, CodeEntity, KnowledgeSource, User
from services.mcp_tokens import find_token_user

router = APIRouter(prefix="/ide", tags=["ide"])
JAVA_IDE_EDGE_TYPES = ("CALLS", "EXTENDS", "IMPLEMENTS", "INSTANTIATES")


def _ide_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    scheme, _, secret = (authorization or "").partition(" ")
    user = find_token_user(db, secret) if scheme.lower() == "bearer" else None
    if user is None:
        raise HTTPException(status_code=401, detail="IDE-Token ungültig", headers={"WWW-Authenticate": "Bearer"})
    return user


@router.get("/file")
def file_annotations(
    response: Response,
    project_id: int,
    source_id: int,
    path: str = Query(min_length=1, max_length=2048),
    variant_key: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
    user: User = Depends(_ide_user),
):
    """Return persisted COBOL and Java references for one exact indexed file."""
    response.headers["Cache-Control"] = "no-store"
    assert_project_visible(project_id, user, db)
    source = db.query(KnowledgeSource).filter(
        KnowledgeSource.id == source_id, KnowledgeSource.project_id == project_id
    ).first()
    if source is None:
        raise HTTPException(status_code=404, detail="Quelle nicht gefunden")
    assert_knowledge_source_visible(source, user, db)

    entities_query = db.query(CodeEntity).filter(
        CodeEntity.project_id == project_id,
        CodeEntity.source_id == source_id,
        CodeEntity.file_path == path,
    )
    if variant_key is not None:
        entities_query = entities_query.filter(CodeEntity.variant_key == variant_key)
    entities = entities_query.order_by(CodeEntity.id).limit(5001).all()
    if not entities:
        raise HTTPException(status_code=404, detail="Datei nicht indiziert")
    if len(entities) > 5000:
        raise HTTPException(status_code=413, detail="Zu viele Entitäten in der Datei")

    entity_ids = [entity.id for entity in entities]
    edge_types = JAVA_IDE_EDGE_TYPES if path.lower().endswith(".java") else ("CALL", "COPY")
    edges = db.query(CodeEdge).filter(
        CodeEdge.project_id == project_id,
        CodeEdge.source_id == source_id,
        CodeEdge.src_entity_id.in_(entity_ids),
        CodeEdge.type.in_(edge_types),
    ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(2001).all()
    if len(edges) > 2000:
        raise HTTPException(status_code=413, detail="Zu viele Referenzen in der Datei")

    targets = {
        entity.id: entity
        for entity in db.query(CodeEntity).filter(
            CodeEntity.id.in_({edge.dst_entity_id for edge in edges if edge.dst_entity_id}),
            CodeEntity.project_id == project_id,
        ).all()
    }
    target_source_ids = {target.source_id for target in targets.values() if target.source_id != source_id}
    target_sources = {
        item.id: item for item in db.query(KnowledgeSource).filter(KnowledgeSource.id.in_(target_source_ids)).all()
    }
    visible_target_sources = set()
    for target_source in target_sources.values():
        try:
            assert_knowledge_source_visible(target_source, user, db)
            visible_target_sources.add(target_source.id)
        except HTTPException:
            pass
    references = []
    for edge in edges:
        meta = edge.meta_json or {}
        target = targets.get(edge.dst_entity_id)
        # A resolved target from another source is shown only when that source
        # is visible to the same user. The occurrence itself remains useful.
        if target and target.source_id != source_id and target.source_id not in visible_target_sources:
            target = None
        references.append({
            "id": edge.id,
            "type": edge.type,
            "name": edge.dst_name,
            "line": edge.src_start_line if edge.src_start_line > 0 else None,
            "start_column": meta.get("symbol_start_column", meta.get("src_start_column")),
            "end_column": meta.get("symbol_end_column", meta.get("src_end_column")),
            "symbol_name": meta.get("method_name") if edge.type == "CALLS" else None,
            "resolution": edge.resolution if target or edge.dst_entity_id is None else "unresolved",
            "resolution_reason": meta.get("resolution_reason"),
            "dispatch_scope": meta.get("dispatch_scope"),
            "target": {
                "id": target.id,
                "name": target.name,
                "file_path": target.file_path,
                "start_line": target.start_line,
                "source_id": target.source_id,
            } if target else None,
        })
    return {"project_id": project_id, "source_id": source_id, "path": path,
            "references": references}
