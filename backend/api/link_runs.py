"""Analyse-Arbeitsfläche des Link-Managers: Menge A gegen Menge B prüfen.

    GET  /projects/{id}/link-runs/options   — Analysearten, Facetten je Mengenart, letzte Auswahl je Analyseart
    GET  /projects/{id}/link-runs/search    — einzelne Objekte einer Mengenart suchen
    POST /projects/{id}/link-runs/preview   — Umfang und Stichprobe einer Menge
    POST /projects/{id}/link-runs/estimate  — Aufwand eines Laufs
    POST /projects/{id}/link-runs           — Lauf starten

Das Mengenformat steht in ``doctus_models.link_sets``; dieselben Mengen liest der Parser aus ``scope_json["sets"]``.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from api.entity_links import estimate_link_computation_scope
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_project_visible
from core.teams import assert_team_visible, is_admin
from doctus_models.database import LinkBuilderRun, Project, User
from doctus_models.link_sets import (
    KINDS,
    PAIRINGS,
    LinkSet,
    Pairing,
    RunSets,
)
from services.link_run_start import (
    active_entity_link_run,
    queue_entity_link_run,
    queue_knowledge_link_run,
)
from services.link_set_options import count_set, kind_options, preview, search

router = APIRouter(prefix="/projects/{project_id}/link-runs", tags=["link_runs"])

# Kandidatenpaare, die ein Dokument↔Dokument-Lauf je Abschnitt höchstens bewertet (cross_link_builder.TOP_MATCHES).
KNOWLEDGE_MATCHES_PER_CHUNK = 5


class LinkRunParamsBody(BaseModel):
    """Dieselben Grenzen wie ``LinkRunParams.LIMITS`` im Parser und die Query-Parameter von ``/compute``."""

    model_config = ConfigDict(extra="forbid")
    top_k_semantic: Optional[int] = Field(None, ge=1, le=200)
    top_k_keyword: Optional[int] = Field(None, ge=1, le=500)
    min_score_semantic: Optional[float] = Field(None, ge=0.0, le=1.0)
    min_score_keyword: Optional[float] = Field(None, ge=0.0, le=1.0)
    merge_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    dedupe_by_chunk: Optional[bool] = None
    review_batch_size: Optional[int] = Field(None, ge=0, le=50)
    review_concurrency: Optional[int] = Field(None, ge=1, le=8)
    embed_window: Optional[int] = Field(None, ge=1, le=20)
    max_review_candidates: Optional[int] = Field(None, ge=0, le=100)
    keyword_selection: Optional[Literal["best", "first"]] = None


class SetsBody(BaseModel):
    pairing: str = "code_docs"
    a: Optional[dict] = None
    b: Optional[dict] = None


class PreviewBody(BaseModel):
    link_set: dict = Field(alias="set")


class StartBody(SetsBody):
    min_confidence: Optional[int] = Field(None, ge=0, le=100)
    max_items: int = Field(200, ge=1, le=5000)
    embedding_model: Optional[str] = Field(None, min_length=1, max_length=255)
    params: LinkRunParamsBody = Field(default_factory=LinkRunParamsBody)


def _visible_project(project_id: int, user: User, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(project.team_id, user, db, "Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)
    return project


def _available(item: Pairing, user: User) -> bool:
    return not item.admin_only or is_admin(user)


def _run_sets(body: SetsBody, user: User) -> RunSets:
    try:
        run_sets = RunSets.from_json(body.model_dump(include={"pairing", "a", "b"}))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not _available(run_sets.pairing, user):
        raise HTTPException(
            status_code=403, detail="Diese Analyseart ist Administratoren vorbehalten"
        )
    return run_sets


def _last_sets(db: Session, project_id: int, item: Pairing) -> dict | None:
    """Auswahl des letzten von einer Person gestarteten Laufs dieser Analyseart; die Auswahl gilt je Projekt."""
    row = (
        db.query(LinkBuilderRun.scope_json)
        .filter(
            LinkBuilderRun.project_id == project_id,
            LinkBuilderRun.task_type == item.task_type,
            LinkBuilderRun.triggered_by_user_id.isnot(None),
        )
        .order_by(LinkBuilderRun.id.desc())
        .first()
    )
    if row is None:
        return None
    scope = row[0] or {}
    try:
        if scope.get("sets"):
            run_sets = RunSets.from_scope(scope, item.key)
            return run_sets.to_json() if run_sets.pairing.key == item.key else None
        if scope.get("source_ids"):
            legacy = LinkSet.from_json(
                {"kind": "docs", "mode": "custom", "facets": {"source": scope["source_ids"]}}
            )
            return RunSets(item, legacy, legacy).to_json()
    except ValueError:
        return None
    return RunSets(item, LinkSet(item.a), LinkSet(item.b)).to_json()


@router.get("/options")
def link_run_options(
    project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    _visible_project(project_id, user, db)
    pairings = [item for item in PAIRINGS if _available(item, user)]
    kinds = sorted({kind for item in pairings for kind in (item.a, item.b)}, key=KINDS.index)
    return {
        "project_id": project_id,
        "pairings": [
            {"key": item.key, "a": item.a, "b": item.b, "task_type": item.task_type}
            for item in pairings
        ],
        "kinds": {kind: kind_options(db, project_id, kind) for kind in kinds},
        "last": {item.key: _last_sets(db, project_id, item) for item in pairings},
    }


@router.get("/search")
def search_link_set_items(
    project_id: int,
    kind: Literal["code", "docs"],
    q: str = Query("", max_length=200),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _visible_project(project_id, user, db)
    return {"items": search(db, project_id, kind, q, limit)}


@router.post("/preview")
def preview_link_set(
    project_id: int,
    body: PreviewBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _visible_project(project_id, user, db)
    try:
        link_set = LinkSet.from_json(body.link_set)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return preview(db, project_id, link_set)


def _estimate(db: Session, project_id: int, run_sets: RunSets, user: User) -> dict:
    item = run_sets.pairing
    if item.task_type == "entity_links" and not run_sets.targeted:
        classic = estimate_link_computation_scope(project_id, db=db, user=user)
        return {
            "pairing": item.key,
            "task_type": item.task_type,
            "targeted": False,
            "is_bootstrap": classic["is_bootstrap"],
            "a_count": classic["entities_to_scan"],
            "b_count": classic["chunk_count"],
            "reviews_max": classic["estimated_llm_reviews_max"],
            "embedding_calls_max": classic["estimated_embedding_calls_max"],
            "has_active_run": classic["has_active_run"],
        }
    a_count = count_set(db, project_id, run_sets.a)["count"]
    b_count = count_set(db, project_id, run_sets.b)["count"]
    to_check = a_count if b_count else 0
    if item.task_type == "entity_links":
        reviews, embeddings = to_check, to_check
        active = active_entity_link_run(db, project_id) is not None
    else:
        reviews, embeddings = to_check * KNOWLEDGE_MATCHES_PER_CHUNK, 0
        active = False
    return {
        "pairing": item.key,
        "task_type": item.task_type,
        "targeted": True,
        "is_bootstrap": False,
        "a_count": a_count,
        "b_count": b_count,
        "reviews_max": reviews,
        "embedding_calls_max": embeddings,
        "has_active_run": active,
    }


@router.post("/estimate")
def estimate_link_run(
    project_id: int,
    body: SetsBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _visible_project(project_id, user, db)
    return _estimate(db, project_id, _run_sets(body, user), user)


@router.post("")
def start_link_run(
    project_id: int,
    body: StartBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _visible_project(project_id, user, db)
    run_sets = _run_sets(body, user)
    for name, link_set in (("A", run_sets.a), ("B", run_sets.b)):
        if link_set.is_empty:
            raise HTTPException(status_code=422, detail=f"Menge {name} ist leer")
    common = {
        "min_confidence": body.min_confidence,
        "embedding_model": body.embedding_model,
        "max_items": body.max_items,
    }
    if run_sets.pairing.task_type == "entity_links":
        result = queue_entity_link_run(
            db,
            user,
            project_id,
            params=body.params.model_dump(exclude_none=True),
            sets=run_sets.to_json() if run_sets.targeted else None,
            **common,
        )
    else:
        result = queue_knowledge_link_run(db, user, project_id, sets=run_sets.to_json(), **common)
    return {**result, "pairing": run_sets.pairing.key, "task_type": run_sets.pairing.task_type}
