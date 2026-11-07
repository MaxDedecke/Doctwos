"""Evidence-backed insights and the minimal O-271/O-301 four-eyes workflow."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from api.schemas import InsightCreate, InsightVerification, InsightReview
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_project_visible, get_project_role
from core.teams import is_admin
from doctus_models.database import Insight, KnowledgeSource, User, DocumentChunk
from doctus_models.insight_evidence import snapshot_evidence
from doctus_models.insight_versions import capture_versions, version_state, versions_match


router = APIRouter(prefix="/projects", tags=["insights"])


def _serialize(insight: Insight, db=None) -> dict:
    current_versions = (
        capture_versions(db, insight.project_id, insight.evidence_json) if db is not None else []
    )
    return {
        "version_bindings": insight.version_bindings,
        "current_versions": current_versions,
        "version_state": version_state(db, insight, current_versions)
        if db is not None
        else "unknown",
        "current_sources": [
            {
                "source_id": source.id,
                "last_synced_at": source.last_synced_at.isoformat()
                if source.last_synced_at
                else None,
                "commit": (source.sync_cursor or {}).get("last_commit"),
                "sync_status": source.sync_status,
            }
            for source in (
                db.query(KnowledgeSource)
                .filter(
                    KnowledgeSource.project_id == insight.project_id,
                    KnowledgeSource.id.in_(
                        [
                            e.get("source_id")
                            for e in insight.evidence_json
                            if e.get("source_id") is not None
                        ]
                    ),
                )
                .all()
                if db is not None
                else []
            )
        ],
        "revision": insight.revision,
        "review_history": insight.review_history or [],
        "id": insight.id,
        "project_id": insight.project_id,
        "title": insight.title,
        "content": insight.content,
        "origin_kind": insight.origin_kind,
        "evidence": insight.evidence_json,
        "status": insight.status,
        "created_by_id": insight.created_by_id,
        "created_at": insight.created_at.isoformat() if insight.created_at else None,
        "verified_by_id": insight.verified_by_id,
        "verified_at": insight.verified_at.isoformat() if insight.verified_at else None,
        "outdated_at": insight.outdated_at.isoformat() if insight.outdated_at else None,
        "outdated_source_ids": insight.outdated_source_ids or [],
    }


def _require_project_admin(
    project_id: int, user: User, db: Session, action: str = "freigeben"
) -> None:
    # Verification changes a shared, user-facing fact. Restrict this first
    # vertical slice to project admins; this is both auditable and maps to the
    # existing permission model without inventing another global role.
    if get_project_role(project_id, user, db) != "admin":
        raise HTTPException(
            status_code=403, detail=f"Nur Projekt-Admins dürfen Erkenntnisse {action}"
        )


@router.post("/{project_id}/insights", status_code=201)
def create_insight(
    project_id: int,
    body: InsightCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_project_visible(project_id, user, db)
    if body.origin_kind not in {"chat", "code", "process"}:
        raise HTTPException(status_code=422, detail="origin_kind muss chat, code oder process sein")
    if not all(isinstance(item, dict) and item for item in body.evidence):
        raise HTTPException(status_code=422, detail="Jeder Beleg muss ein nicht-leeres Objekt sein")

    source_ids = {
        item.get("source_id") for item in body.evidence if isinstance(item.get("source_id"), int)
    }
    sources = (
        {
            source.id: source
            for source in db.query(KnowledgeSource)
            .filter(KnowledgeSource.id.in_(source_ids), KnowledgeSource.project_id == project_id)
            .all()
        }
        if source_ids
        else {}
    )
    evidence = []
    for item in snapshot_evidence(db, project_id, body.evidence):
        snapshot = dict(item)
        source = sources.get(snapshot.get("source_id"))
        if source is None and snapshot.get("source_id") is not None:
            source = (
                db.query(KnowledgeSource)
                .filter_by(id=snapshot["source_id"], project_id=project_id)
                .first()
            )
        if source:
            snapshot["source_last_synced_at"] = (
                source.last_synced_at.isoformat() if source.last_synced_at else None
            )
        evidence.append(snapshot)

    insight = Insight(
        project_id=project_id,
        title=body.title.strip(),
        content=body.content.strip(),
        origin_kind=body.origin_kind,
        evidence_json=evidence,
        version_bindings=capture_versions(db, project_id, evidence, dependencies=True),
        status="draft",
        created_by_id=user.id,
    )
    db.add(insight)
    db.commit()
    db.refresh(insight)
    return _serialize(insight, db)


@router.delete("/{project_id}/insights/{insight_id}", status_code=204)
def delete_insight(
    project_id: int,
    insight_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_project_visible(project_id, user, db)
    _require_project_admin(project_id, user, db, "löschen")
    insight = (
        db.query(Insight).filter(Insight.id == insight_id, Insight.project_id == project_id).first()
    )
    if not insight:
        raise HTTPException(status_code=404, detail="Erkenntnis nicht gefunden")
    db.delete(insight)
    db.commit()
    return Response(status_code=204)


@router.get("/{project_id}/insights")
def list_insights(
    project_id: int,
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_project_visible(project_id, user, db)
    query = db.query(Insight).filter(Insight.project_id == project_id)
    if status is not None:
        if status not in {"draft", "verified", "outdated", "rejected"}:
            raise HTTPException(status_code=422, detail="Unbekannter Erkenntnisstatus")
        query = query.filter(Insight.status == status)
    return [
        _serialize(insight, db)
        for insight in query.order_by(Insight.created_at.desc(), Insight.id.desc()).all()
    ]


@router.post("/{project_id}/insights/{insight_id}/verify")
def verify_insight(
    project_id: int,
    insight_id: int,
    body: InsightVerification,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_project_visible(project_id, user, db)
    _require_project_admin(project_id, user, db)
    if not body.confirm:
        raise HTTPException(
            status_code=422, detail="Die Freigabe muss ausdrücklich bestätigt werden"
        )
    insight = (
        db.query(Insight).filter(Insight.id == insight_id, Insight.project_id == project_id).first()
    )
    if not insight:
        raise HTTPException(status_code=404, detail="Erkenntnis nicht gefunden")
    db.refresh(insight, with_for_update=True)
    if body.expected_revision is not None and insight.revision != body.expected_revision:
        raise HTTPException(status_code=409, detail="Erkenntnis wurde zwischenzeitlich geändert")
    needs_version_review = insight.status == "verified" and version_state(db, insight) not in {
        "current",
        "project",
    }
    if insight.status not in {"draft", "outdated"} and not needs_version_review:
        raise HTTPException(status_code=409, detail="Erkenntnis wurde bereits freigegeben")
    if insight.created_by_id == user.id and not is_admin(user):
        raise HTTPException(
            status_code=403, detail="Ersteller dürfen ihre eigene Erkenntnis nicht freigeben"
        )

    try:
        current_versions = capture_versions(
            db, project_id, insight.evidence_json, dependencies=True, strict=True
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not current_versions and version_state(db, insight) == "unbound":
        raise HTTPException(
            status_code=409, detail="Belege sind keiner eindeutigen Quelle zugeordnet"
        )
    expected = body.expected_versions
    if expected is None:
        expected = insight.version_bindings
    if current_versions and (expected is None or not versions_match(expected, current_versions)):
        raise HTTPException(
            status_code=409,
            detail="Quellenstand hat sich geändert; bitte Commit und Analysekontext erneut prüfen",
        )
    _record_review(insight, user, "verify")
    insight.version_bindings = current_versions
    insight.evidence_json = _current_evidence(db, project_id, insight.evidence_json)
    insight.outdated_at = None
    insight.outdated_source_ids = []
    insight.status = "verified"
    insight.verified_by_id = user.id
    insight.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(insight)
    return _serialize(insight, db)


def _record_review(insight, user, action):
    insight.review_history = [
        *(insight.review_history or []),
        {
            "revision": insight.revision,
            "action": action,
            "user_id": user.id,
            "created_by_id": insight.created_by_id,
            "version_bindings": insight.version_bindings,
            "at": datetime.now(timezone.utc).isoformat(),
            "title": insight.title,
            "content": insight.content,
            "evidence": insight.evidence_json,
            "status": insight.status,
            "verified_by_id": insight.verified_by_id,
            "verified_at": insight.verified_at.isoformat() if insight.verified_at else None,
        },
    ]
    insight.revision += 1


def _current_evidence(db, project_id, evidence):
    result = []
    for item in snapshot_evidence(db, project_id, evidence):
        snapshot = dict(item)
        source_id = snapshot.get("source_id")
        if source_id is not None:
            source = (
                db.query(KnowledgeSource).filter_by(id=source_id, project_id=project_id).first()
            )
            if not source or source.sync_status != "completed":
                raise HTTPException(
                    status_code=409, detail="Belegquelle fehlt oder ist nicht synchronisiert"
                )
            if (
                snapshot.get("file")
                and not db.query(DocumentChunk.id)
                .filter_by(project_id=project_id, source_id=source_id, file_path=snapshot["file"])
                .first()
            ):
                raise HTTPException(status_code=409, detail="Belegdatei fehlt im aktuellen Index")
            snapshot["source_last_synced_at"] = (
                source.last_synced_at.isoformat() if source.last_synced_at else None
            )
        if source_id is not None:
            snapshot["source_commit"] = (source.sync_cursor or {}).get("last_commit")
        result.append(snapshot)
    return result


@router.post("/{project_id}/insights/{insight_id}/review")
def review_insight(
    project_id: int,
    insight_id: int,
    body: InsightReview,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_project_visible(project_id, user, db)
    _require_project_admin(project_id, user, db, "überarbeiten")
    insight = (
        db.query(Insight).filter_by(id=insight_id, project_id=project_id).with_for_update().first()
    )
    if not insight:
        raise HTTPException(status_code=404, detail="Erkenntnis nicht gefunden")
    if insight.revision != body.expected_revision:
        raise HTTPException(status_code=409, detail="Erkenntnis wurde zwischenzeitlich geändert")
    if body.action == "revise" and (
        not body.title or not body.title.strip() or not body.content or not body.content.strip()
    ):
        raise HTTPException(status_code=422, detail="Titel und Aussage sind erforderlich")
    _record_review(insight, user, body.action)
    if body.action == "revise":
        insight.title, insight.content = body.title.strip(), body.content.strip()
        insight.created_by_id = user.id
        insight.status = "draft"
    else:
        insight.status = "rejected"
    insight.verified_by_id = None
    insight.verified_at = None
    db.commit()
    db.refresh(insight)
    return _serialize(insight, db)


@router.get("/{project_id}/insights/commit-sources")
def commit_sources(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assert_project_visible(project_id, user, db)
    return [
        {
            "id": source.id,
            "name": source.name,
            "branch": source.branch,
            "indexed_commit": (source.sync_cursor or {}).get("last_commit"),
            "sync_status": source.sync_status,
        }
        for source in db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.project_id == project_id,
            KnowledgeSource.type.ilike("git"),
        )
        .order_by(KnowledgeSource.id)
        .all()
    ]


@router.get("/{project_id}/insights/commit-check")
def inspect_commit_insights(
    project_id: int,
    source_id: int = Query(ge=1),
    target_ref: str = Query(min_length=1, max_length=256),
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=25),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from services.insight_commit_check import check_commit

    assert_project_visible(project_id, user, db)
    try:
        return check_commit(db, project_id, source_id, target_ref, after_id=after_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
