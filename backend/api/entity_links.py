"""
backend/api/entity_links.py
============================
Link Manager: Verwaltung von Verknüpfungen zwischen Code-Entities und Wissens-Dokumenten.

Endpunkte:
    GET  /projects/{project_id}/link-recommendations   — Alle Links mit Zähler-Zusammenfassung
    POST /projects/{project_id}/link-recommendations   — Manuellen Link anlegen (sofort "approved")
    POST /projects/{project_id}/link-recommendations/compute — Link-Berechnung starten (Celery)
    PATCH /entity-doc-links/{id}                        — Status auf "approved" / "rejected" setzen
    POST /entity-doc-links/{id}/llm-review              — Einzelnen Link erneut vom LLM bewerten lassen
    DELETE /entity-doc-links/{id}                       — Link löschen
    GET  /projects/{project_id}/entities/{id}/links    — Alle approved Links einer Entity
    GET  /projects/{project_id}/doc-chunks/search      — Dokument-Chunks durchsuchen (für Titel-Picker)
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

import core.config as cfg
from api.schemas import LinkStatusUpdate, LlmReviewRequest, ManualLinkCreate
from api.serializers import serialize_link
from core.config import celery_app
from core.tracing import get_trace_id
from core.db_setup import get_db
from models.database import CodeEntity, DocumentChunk, EntityDocLink, KnowledgeSource, LinkBuilderRun, Project, User
from core.auth_dependency import get_current_user
from core.teams import assert_team_visible
from core.projects import assert_project_visible
from services.ollama_client import ask_llm_json_for_profile


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
    min_confidence: Optional[int] = Query(None, ge=0, le=100, description="Vom Nutzer eingestellte Mindest-Wahrscheinlichkeit (%) für die LLM-Bewertung, ab der ein Kandidat als Vorschlag gespeichert wird."),
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

    celery_app.send_task(
        "compute_entity_links",
        args=[run.id, project_id],
        kwargs={"trace_id": get_trace_id(), "min_confidence": min_confidence},
    )
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

    if body.status is not None:
        if body.status not in ("approved", "rejected"):
            raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")
        link.status = body.status
        link.reviewed_at = datetime.now(timezone.utc)
    # Beschreibung ist unabhängig vom Status editierbar (leerer String löscht sie
    # wieder) — erlaubt Nutzern, präziser festzuhalten, wie Code und Dokument
    # inhaltlich zusammenhängen, statt sich auf die automatische LLM-Begründung
    # zu verlassen.
    if body.context is not None:
        link.context = body.context.strip() or None
    db.commit()
    return serialize_link(link)


@router.post("/entity-doc-links/{link_id}/llm-review")
async def llm_review_link(
    link_id: int,
    body: LlmReviewRequest = LlmReviewRequest(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Bewertet einen einzelnen Link erneut per LLM (auf Nutzer-Klick im Link Manager,
    nicht Teil des Batch-Scans in parser/tasks/link_builder.py). Ersetzt score/context
    durch das LLM-Urteil, ändert aber bewusst NICHT den Status — der Nutzer entscheidet
    danach selbst per Bestätigen/Ablehnen. Nutzt das im Link-Manager-Header aktive
    LLM-Profil (body.llm_*, vom Frontend mitgeschickt) statt fix das lokale Ollama —
    für Cloud-Provider greift dasselbe Opt-in-Gate wie beim normalen Chat (api/chat.py).
    """
    requested_provider = (body.llm_provider or "ollama").lower()
    if requested_provider in cfg.CLOUD_LLM_PROVIDERS and not cfg.cloud_llm_allowed():
        raise HTTPException(
            status_code=403,
            detail=(
                f"Cloud-LLM-Provider '{requested_provider}' ist für dieses Deployment deaktiviert "
                "(config/features.json: llm.allowCloudProviders). Bitte ein lokales Ollama-Profil verwenden."
            ),
        )

    link = db.query(EntityDocLink).filter(EntityDocLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link nicht gefunden")

    proj = db.query(Project).filter(Project.id == link.project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Link nicht gefunden")
    assert_project_visible(link.project_id, user, db)

    entity = db.query(CodeEntity).filter(CodeEntity.id == link.entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Code-Entity nicht gefunden")

    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == link.chunk_id).first() if link.chunk_id else None
    if not chunk:
        raise HTTPException(status_code=400, detail="Kein Dokument-Inhalt zu diesem Link vorhanden — manuell angelegte Links können nicht geprüft werden")

    prompt = (
        "Du bist ein Programmier- und Code-Dokumentations-Experte.\n"
        "Bewerte, wie relevant der folgende Dokumentationsabschnitt für diese Code-Entity ist:\n"
        f"Entity: [{entity.type}] {entity.name} in Datei '{entity.file_path}'\n\n"
        f"Dokument [{link.source_type or '—'}] '{link.doc_title}':\n{(chunk.content or '')[:250]}...\n\n"
        "Antworte NUR mit einem JSON-Objekt der Form "
        '{"confidence": <Ganzzahl 0-100, wie sicher du bezüglich der Relevanz bist>, '
        '"reason": "<kurze Begründung auf Deutsch, 1-2 Sätze>"}.'
    )

    try:
        data = await ask_llm_json_for_profile(
            prompt,
            provider=requested_provider,
            model=body.llm_model,
            api_key=body.llm_api_key,
            base_url=body.llm_base_url,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM-Prüfung fehlgeschlagen: {e}")

    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        raise HTTPException(status_code=502, detail="LLM lieferte keine gültige Konfidenz")

    link.score = round(max(0.0, min(100.0, float(confidence))) / 100.0, 4)
    if data.get("reason"):
        link.context = data["reason"]
    db.commit()
    db.refresh(link)
    return serialize_link(link, entity)


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
