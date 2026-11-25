"""Wechsel des Embedding-Modells je Projekt (Ablauf in ``parser/tasks/embedding_migration.py``).

Lesen dürfen Projektmitglieder (Abdeckung und Stand); starten, umschalten, zurücknehmen und aufräumen nur Admins.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_project_visible
from core.teams import require_admin
from codena_models.database import (
    DocumentChunk,
    EmbeddingMigration,
    EmbeddingProfile,
    KnowledgeSource,
    Project,
    User,
)
from services.answer_context import _embedding_profile_for_project
from services.job_control import send_tracked_task

router = APIRouter(
    prefix="/projects/{project_id}/embedding-migration", tags=["embedding-migration"]
)

OPEN_STATES = ("embedding", "ready", "switched", "failed")
_NEXT = {
    "switch": ("ready",),
    "rollback": ("switched",),
    "cleanup": ("switched", "rolled_back", "cancelled", "failed"),
}


class StartRequest(BaseModel):
    profile_id: int


def _scope(db: Session, project_id: int):
    source_ids = [
        sid
        for (sid,) in db.query(KnowledgeSource.id).filter(KnowledgeSource.project_id == project_id)
    ]
    scope = DocumentChunk.project_id == project_id
    if source_ids:
        scope = or_(
            scope,
            and_(DocumentChunk.project_id.is_(None), DocumentChunk.source_id.in_(source_ids)),
        )
    return scope


def _serialize(m: EmbeddingMigration | None) -> dict | None:
    if m is None:
        return None
    return {
        "id": m.id,
        "status": m.status,
        "target_model": m.target_model,
        "target_dimension": m.target_dimension,
        "previous_model": m.previous_model,
        "profile_id": m.profile_id,
        "total": m.total,
        "done": m.done,
        "error": m.error,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "switched_at": m.switched_at.isoformat() if m.switched_at else None,
    }


def _latest(db: Session, project_id: int) -> EmbeddingMigration | None:
    return (
        db.query(EmbeddingMigration)
        .filter(EmbeddingMigration.project_id == project_id)
        .order_by(EmbeddingMigration.id.desc())
        .first()
    )


def _project(db: Session, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    return project


@router.get("")
def state(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Abdeckung je Modell, Profil des Projekts und der letzte Modellwechsel."""
    _project(db, project_id)
    assert_project_visible(project_id, user, db)
    models = {
        (model or "unbekannt"): count
        for model, count in db.query(DocumentChunk.embedding_model, func.count(DocumentChunk.id))
        .filter(_scope(db, project_id), DocumentChunk.embedding.isnot(None))
        .group_by(DocumentChunk.embedding_model)
        .all()
    }
    without = (
        db.query(func.count(DocumentChunk.id))
        .filter(_scope(db, project_id), DocumentChunk.embedding.is_(None))
        .scalar()
    )
    try:
        profile = _embedding_profile_for_project(db, project_id)
        current = {"id": profile.id, "name": profile.name, "model": profile.model}
    except LookupError:
        current = None
    return {
        "project_id": project_id,
        "models": models,
        "without_embedding": without or 0,
        "project_profile": current,
        "migration": _serialize(_latest(db, project_id)),
    }


@router.post("", status_code=202)
def start(
    project_id: int,
    body: StartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    _project(db, project_id)
    latest = _latest(db, project_id)
    if latest is not None and latest.status in OPEN_STATES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ein Modellwechsel ist noch offen (Status {latest.status}). Erst abschließen, zurücknehmen "
                "oder aufräumen."
            ),
        )
    profile = db.query(EmbeddingProfile).filter(EmbeddingProfile.id == body.profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Embedding-Profil nicht gefunden")
    if db.query(EmbeddingProfile).filter(EmbeddingProfile.model == profile.model).count() > 1:
        raise HTTPException(
            status_code=409,
            detail=f"Mehrere Profile nutzen '{profile.model}'; das Zielmodell muss eindeutig einem Profil gehören.",
        )
    try:
        previous = _embedding_profile_for_project(db, project_id).model
    except LookupError:
        previous = None
    models = {
        model
        for (model,) in db.query(DocumentChunk.embedding_model)
        .filter(_scope(db, project_id), DocumentChunk.embedding.isnot(None))
        .distinct()
    }
    if models == {profile.model}:
        raise HTTPException(status_code=409, detail=f"Das Projekt nutzt bereits '{profile.model}'.")
    if len(models - {profile.model}) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Das Projekt liegt in mehreren Vektorräumen ("
                + ", ".join(sorted(m or "unbekannt" for m in models))
                + "); Quellen erst einheitlich neu einlesen."
            ),
        )
    total = db.query(func.count(DocumentChunk.id)).filter(_scope(db, project_id)).scalar() or 0
    migration = EmbeddingMigration(
        project_id=project_id,
        profile_id=profile.id,
        target_model=profile.model,
        target_dimension=profile.dimension,
        previous_model=next(iter(models - {profile.model}), None) or previous,
        status="embedding",
        total=total,
        done=0,
        created_by_user_id=user.id,
    )
    db.add(migration)
    db.commit()
    send_tracked_task(db, migration, "embedding_migration", [migration.id, "run"])
    return _serialize(migration)


@router.post("/{migration_id}/{action}", status_code=202)
def act(
    project_id: int,
    migration_id: int,
    action: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    migration = (
        db.query(EmbeddingMigration)
        .filter(EmbeddingMigration.id == migration_id, EmbeddingMigration.project_id == project_id)
        .first()
    )
    if migration is None:
        raise HTTPException(status_code=404, detail="Modellwechsel nicht gefunden")
    if action == "cancel":
        if migration.status not in ("embedding", "ready", "failed"):
            raise HTTPException(
                status_code=409, detail="Nur ein nicht umgeschalteter Wechsel lässt sich abbrechen."
            )
        migration.status = "cancelled"
        db.commit()
        send_tracked_task(db, migration, "embedding_migration", [migration.id, "cleanup"])
        return _serialize(migration)
    if action == "resume":
        if migration.status != "failed":
            raise HTTPException(
                status_code=409, detail="Nur ein fehlgeschlagener Lauf lässt sich fortsetzen."
            )
        send_tracked_task(db, migration, "embedding_migration", [migration.id, "run"])
        return _serialize(migration)
    if action not in _NEXT:
        raise HTTPException(status_code=404, detail="Unbekannte Aktion")
    if migration.status not in _NEXT[action]:
        raise HTTPException(
            status_code=409,
            detail=f"'{action}' ist im Status {migration.status} nicht möglich.",
        )
    migration.error = None
    db.commit()
    send_tracked_task(db, migration, "embedding_migration", [migration.id, action])
    return _serialize(migration)
