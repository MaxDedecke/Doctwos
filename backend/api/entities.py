"""COBOL-Fokusobjekte und ihre direkte Nachbarschaft (F-067)."""

from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_project_code_visible_in_context, assert_project_visible
from core.teams import assert_team_visible
from models.database import CodeEdge, CodeEntity, DocumentChunk, KnowledgeSource, Project, User

router = APIRouter(prefix="/entities", tags=["entities"])


def _assert_entity_visible(entity: CodeEntity, user: User, db: Session, project_context_id: int | None = None) -> None:
    if entity.project_id is not None:
        project = db.query(Project).filter(Project.id == entity.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Entity nicht gefunden")
        assert_team_visible(project.team_id, user, db, "Entity nicht gefunden")
        assert_project_visible(entity.project_id, user, db)
        # Team-/Projekt-Mitgliedschaft ist die Basis-Sichtbarkeit, reicht aber allein nicht
        # -- außerhalb des eigenen Projekt-Kontexts (kein project_context_id oder ein ANDERES
        # Projekt, z.B. "Allgemein"-Suche/-Graph-View) braucht das Projekt zusätzlich das
        # explizite Opt-in expose_code_analysis_globally. Siehe core/projects.py.
        assert_project_code_visible_in_context(entity.project_id, project_context_id, db, "Entity nicht gefunden")
    if entity.source_id is not None:
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == entity.source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="Entity nicht gefunden")
        assert_team_visible(source.team_id, user, db, "Entity nicht gefunden")


def entity_json(entity: CodeEntity) -> dict:
    return {
        "id": entity.id, "project_id": entity.project_id, "source_id": entity.source_id,
        "parent_id": entity.parent_id, "name": entity.name, "qualified_name": entity.qualified_name,
        "type": entity.type, "file_path": entity.file_path, "start_line": entity.start_line,
        "end_line": entity.end_line, "meta": entity.meta_json or {},
    }


def _definition(entity: CodeEntity, db: Session) -> dict | None:
    query = db.query(DocumentChunk).filter(
        DocumentChunk.project_id == entity.project_id,
        DocumentChunk.source_id == entity.source_id,
        DocumentChunk.file_path == entity.file_path,
    )
    if entity.start_line is not None and entity.end_line is not None:
        query = query.filter(
            DocumentChunk.start_line <= entity.end_line,
            DocumentChunk.end_line >= entity.start_line,
        )
    chunk = query.order_by(DocumentChunk.start_line, DocumentChunk.id).first()
    if not chunk:
        return None
    return {"chunk_id": chunk.id, "content": chunk.content, "start_line": chunk.start_line, "end_line": chunk.end_line}


@router.get("/resolve")
def resolve_entity(
    source_id: int,
    path: str,
    project_id: int | None = Query(default=None, description="Aktueller Projekt-Kontext des Aufrufers (z.B. Code-Editor); None im Allgemein-Modus"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Quelle nicht gefunden")
    assert_team_visible(source.team_id, user, db, "Quelle nicht gefunden")
    suffix = PurePosixPath(path).suffix.lower()
    wanted_type = "copybook" if suffix in {".cpy", ".copy"} else "program"
    entity = db.query(CodeEntity).filter(
        CodeEntity.source_id == source_id,
        CodeEntity.file_path == path,
        CodeEntity.type == wanted_type,
    ).order_by(CodeEntity.id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(entity, user, db, project_id)
    return entity_json(entity)


@router.get("/{entity_id}")
def get_entity(
    entity_id: int,
    project_id: int | None = Query(default=None, description="Aktueller Projekt-Kontext des Aufrufers (z.B. Code-Editor); None im Allgemein-Modus"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entity = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(entity, user, db, project_id)
    return {**entity_json(entity), "definition": _definition(entity, db)}


@router.get("/{entity_id}/neighbors")
def get_neighbors(
    entity_id: int,
    types: list[str] | None = Query(default=None),
    direction: str = Query(default="both", pattern="^(in|out|both)$"),
    project_id: int | None = Query(default=None, description="Aktueller Projekt-Kontext des Aufrufers (z.B. Code-Editor); None im Allgemein-Modus"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entity = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(entity, user, db, project_id)
    requested = {item.upper() for value in (types or []) for item in value.split(",") if item}
    clauses = []
    if direction in {"out", "both"}:
        clauses.append(CodeEdge.src_entity_id == entity_id)
    if direction in {"in", "both"}:
        clauses.append(CodeEdge.dst_entity_id == entity_id)
    query = db.query(CodeEdge).filter(or_(*clauses))
    if requested:
        query = query.filter(CodeEdge.type.in_(requested))
    groups: dict[str, list[dict]] = {}
    for edge in query.order_by(CodeEdge.type, CodeEdge.id).all():
        edge_direction = "out" if edge.src_entity_id == entity_id else "in"
        other_id = edge.dst_entity_id if edge_direction == "out" else edge.src_entity_id
        other = db.query(CodeEntity).filter(CodeEntity.id == other_id).first() if other_id else None
        key = f"{edge.type}:{edge_direction}"
        groups.setdefault(key, []).append({
            "edge_id": edge.id, "type": edge.type, "direction": edge_direction,
            "resolution": edge.resolution, "dst_name": edge.dst_name,
            "entity": entity_json(other) if other else None,
            "start_line": edge.src_start_line, "end_line": edge.src_end_line,
        })
    return {"entity": entity_json(entity), "groups": groups}
