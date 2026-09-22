"""Evidence-backed insights and the minimal O-271/O-301 four-eyes workflow."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.schemas import InsightCreate, InsightVerification
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_project_visible, get_project_role
from models.database import Insight, User


router = APIRouter(prefix="/projects", tags=["insights"])


def _serialize(insight: Insight) -> dict:
    return {
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
    }


def _require_project_admin(project_id: int, user: User, db: Session) -> None:
    # Verification changes a shared, user-facing fact. Restrict this first
    # vertical slice to project admins; this is both auditable and maps to the
    # existing permission model without inventing another global role.
    if get_project_role(project_id, user, db) != "admin":
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins dürfen Erkenntnisse freigeben")


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

    insight = Insight(
        project_id=project_id,
        title=body.title.strip(),
        content=body.content.strip(),
        origin_kind=body.origin_kind,
        evidence_json=body.evidence,
        status="draft",
        created_by_id=user.id,
    )
    db.add(insight)
    db.commit()
    db.refresh(insight)
    return _serialize(insight)


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
        if status not in {"draft", "verified"}:
            raise HTTPException(status_code=422, detail="Unbekannter Erkenntnisstatus")
        query = query.filter(Insight.status == status)
    return [_serialize(insight) for insight in query.order_by(Insight.created_at.desc(), Insight.id.desc()).all()]


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
        raise HTTPException(status_code=422, detail="Die Freigabe muss ausdrücklich bestätigt werden")
    insight = db.query(Insight).filter(Insight.id == insight_id, Insight.project_id == project_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Erkenntnis nicht gefunden")
    if insight.status != "draft":
        raise HTTPException(status_code=409, detail="Erkenntnis wurde bereits freigegeben")
    if insight.created_by_id == user.id:
        raise HTTPException(status_code=403, detail="Ersteller dürfen ihre eigene Erkenntnis nicht freigeben")

    insight.status = "verified"
    insight.verified_by_id = user.id
    insight.verified_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(insight)
    return _serialize(insight)
