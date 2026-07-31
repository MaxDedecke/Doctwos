"""
backend/api/entity_links.py
============================
Link Manager: Verwaltung von Verknüpfungen zwischen Code-Entities und Wissens-Dokumenten.

Endpunkte:
    GET  /projects/{project_id}/link-recommendations   — Alle Links mit Zähler-Zusammenfassung
    POST /projects/{project_id}/link-recommendations   — Manuellen Link anlegen (sofort "approved")
    POST /projects/{project_id}/link-recommendations/compute — Link-Berechnung starten (Celery)
    PATCH /entity-doc-links/{id}                        — Status auf "approved" / "rejected" setzen
    DELETE /entity-doc-links/{id}                       — Link löschen
    GET  /projects/{project_id}/entities/{id}/links    — Alle approved Links einer Entity
    GET  /projects/{project_id}/doc-chunks/search      — Dokument-Chunks durchsuchen (für Titel-Picker)
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.schemas import LinkStatusUpdate, ManualLinkCreate
from api.serializers import serialize_link
from core.config import celery_app
from core.tracing import get_trace_id
from core.db_setup import get_db
from models.database import CodeEntity, DocumentChunk, EntityDocLink, KnowledgeSource, LinkBuilderRun, Project, User
from core.auth_dependency import get_current_user
from core.teams import assert_team_visible
from core.projects import assert_project_visible


def _serialize_link_builder_run(run: LinkBuilderRun) -> dict:
    return {
        "id": run.id,
        "task_type": run.task_type,
        "project_id": run.project_id,
        "status": run.status,
        "progress_message": run.progress_message,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "links_created": run.links_created,
    }

router = APIRouter(tags=["entity_links"])


@router.get("/projects/{project_id}/link-recommendations")
def get_link_recommendations(
    project_id: int,
    status: Optional[str] = None,
    min_score: Optional[float] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)

    q = db.query(EntityDocLink).filter(EntityDocLink.project_id == project_id)
    if status:
        q = q.filter(EntityDocLink.status == status)
    if min_score is not None:
        q = q.filter(
            (EntityDocLink.score >= min_score) | (EntityDocLink.score == None)
        )
    links = q.order_by(EntityDocLink.score.desc().nullslast(), EntityDocLink.created_at.desc()).all()

    # Preload entities for serialization to avoid N+1 queries
    entity_ids = {lnk.entity_id for lnk in links}
    entities = {e.id: e for e in db.query(CodeEntity).filter(CodeEntity.id.in_(entity_ids)).all()}

    # Calculate counts for UI badges
    counts = {
        "pending": db.query(EntityDocLink).filter(EntityDocLink.project_id == project_id, EntityDocLink.status == "pending").count(),
        "approved": db.query(EntityDocLink).filter(EntityDocLink.project_id == project_id, EntityDocLink.status == "approved").count(),
        "rejected": db.query(EntityDocLink).filter(EntityDocLink.project_id == project_id, EntityDocLink.status == "rejected").count(),
    }

    return {
        "counts": counts,
        "links": [serialize_link(lnk, entities.get(lnk.entity_id)) for lnk in links]
    }


@router.post("/projects/{project_id}/link-recommendations")
def create_manual_link(
    project_id: int,
    body: ManualLinkCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)

    entity = db.query(CodeEntity).filter(
        CodeEntity.id == body.entity_id, CodeEntity.project_id == project_id
    ).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Code entity not found")

    # Duplicate check
    existing = db.query(EntityDocLink).filter(
        EntityDocLink.entity_id == body.entity_id,
        EntityDocLink.doc_title == body.doc_title,
        EntityDocLink.status == "approved"
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This link already exists")

    link = EntityDocLink(
        project_id=project_id,
        entity_id=body.entity_id,
        doc_title=body.doc_title,
        doc_url=body.doc_url,
        source_type=body.source_type,
        score=None,
        link_type="manual",
        context=body.context,
        status="approved",
        created_by="user"
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return serialize_link(link, entity)


@router.post("/projects/{project_id}/link-recommendations/compute")
def trigger_link_computation(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)

    # Ein Refresh startet den Scan von neuem — bisher unbestätigte (pending)
    # Vorschläge sind per Definition noch nicht reviewt und würden sonst neben
    # den frisch berechneten Vorschlägen als Karteileichen liegen bleiben.
    # Approved/rejected Links bleiben unangetastet.
    db.query(EntityDocLink).filter(
        EntityDocLink.project_id == project_id,
        EntityDocLink.status == "pending"
    ).delete(synchronize_session=False)

    run = LinkBuilderRun(task_type="entity_links", project_id=project_id, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)

    celery_app.send_task("compute_entity_links", args=[run.id, project_id], kwargs={"trace_id": get_trace_id()})
    return {"message": "Link computation started", "project_id": project_id, "run_id": run.id}


@router.get("/projects/{project_id}/link-builder-runs")
def list_link_builder_runs(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    History of /link-recommendations/compute invocations for a project (most
    recent first) — including runs that crashed or found 0 new links, so a
    silent failure stays distinguishable from a clean run that found nothing.
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)

    runs = (
        db.query(LinkBuilderRun)
        .filter(LinkBuilderRun.task_type == "entity_links", LinkBuilderRun.project_id == project_id)
        .order_by(LinkBuilderRun.created_at.desc())
        .all()
    )
    return [_serialize_link_builder_run(r) for r in runs]


@router.patch("/entity-doc-links/{link_id}")
def update_link_status(
    link_id: int,
    body: LinkStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    link = db.query(EntityDocLink).filter(EntityDocLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link nicht gefunden")
    
    proj = db.query(Project).filter(Project.id == link.project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Link nicht gefunden")
    assert_project_visible(link.project_id, user, db)

    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")
    link.status = body.status
    link.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return serialize_link(link)


@router.delete("/entity-doc-links/{link_id}")
def delete_link(
    link_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    link = db.query(EntityDocLink).filter(EntityDocLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link nicht gefunden")
    
    proj = db.query(Project).filter(Project.id == link.project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Link nicht gefunden")
    assert_project_visible(link.project_id, user, db)

    db.delete(link)
    db.commit()
    return {"message": "Link deleted"}


@router.get("/projects/{project_id}/entities/{entity_id}/links")
def get_entity_links(
    project_id: int,
    entity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)

    links = db.query(EntityDocLink).filter(
        EntityDocLink.project_id == project_id,
        EntityDocLink.entity_id == entity_id,
        EntityDocLink.status == "approved"
    ).order_by(EntityDocLink.score.desc().nullslast()).all()
    return [serialize_link(lnk) for lnk in links]


@router.get("/projects/{project_id}/doc-chunks/search")
def search_doc_chunks(
    project_id: int,
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)

    source_ids = db.query(KnowledgeSource.id).filter(KnowledgeSource.project_id == project_id).subquery()
    query = db.query(
        DocumentChunk.file_path, DocumentChunk.metadata_json, DocumentChunk.source_id
    ).filter(DocumentChunk.source_id.in_(source_ids))
    if q:
        query = query.filter(or_(
            DocumentChunk.file_path.ilike(f"%{q}%"),
            DocumentChunk.metadata_json['title'].as_string().ilike(f"%{q}%"),
        ))
    rows = query.distinct(DocumentChunk.file_path).limit(20).all()

    results = []
    seen: set[str] = set()
    for file_path, meta, source_id in rows:
        title = (meta or {}).get("title") or file_path
        if title not in seen:
            seen.add(title)
            results.append({
                "title": title,
                "url": (meta or {}).get("url"),
                "source_type": (meta or {}).get("source_type")
            })
    return results
