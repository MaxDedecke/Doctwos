"""Admin settings and manual export for opt-in chat-feedback diagnostics (O-088)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api.schemas import ChatFeedbackDiagnosticSettingsUpdate
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.teams import require_admin
from models.database import ChatFeedbackDiagnosticCase, User
from services.chat_feedback_diagnostics import get_settings, purge_expired_cases

router = APIRouter(prefix="/feedback-diagnostics", tags=["feedback-diagnostics"])


def _serialize_settings(settings) -> dict:
    return {
        "collection_enabled": settings.collection_enabled,
        "support_export_enabled": settings.support_export_enabled,
        "retention_days": settings.retention_days,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
    }


def _serialize_case(case: ChatFeedbackDiagnosticCase) -> dict:
    return {
        "id": case.id,
        "message_id": case.chat_message_id,
        "project_id": case.project_id,
        "source_id": case.source_id,
        "question": case.question,
        "answer": case.answer,
        "sources_json": case.sources_json or [],
        "model": case.model,
        "provider": case.provider,
        "created_at": case.created_at.isoformat() if case.created_at else None,
    }


@router.get("/settings")
def read_settings(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return _serialize_settings(get_settings(db))


@router.patch("/settings")
def update_settings(
    body: ChatFeedbackDiagnosticSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if not 1 <= body.retention_days <= 365:
        raise HTTPException(status_code=400, detail="Aufbewahrungsfrist muss zwischen 1 und 365 Tagen liegen")
    settings = get_settings(db)
    settings.collection_enabled = body.collection_enabled
    settings.support_export_enabled = body.support_export_enabled if body.collection_enabled else False
    settings.retention_days = body.retention_days
    settings.updated_by_user_id = user.id
    purge_expired_cases(db, settings.retention_days)
    db.commit()
    db.refresh(settings)
    return _serialize_settings(settings)


@router.get("/cases")
def list_cases(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    settings = get_settings(db)
    purge_expired_cases(db, settings.retention_days)
    db.commit()
    cases = (
        db.query(ChatFeedbackDiagnosticCase)
        .order_by(ChatFeedbackDiagnosticCase.created_at.desc(), ChatFeedbackDiagnosticCase.id.desc())
        .limit(limit)
        .all()
    )
    return {"entries": [_serialize_case(case) for case in cases], "total": len(cases)}


@router.delete("/cases")
def delete_cases(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    deleted = db.query(ChatFeedbackDiagnosticCase).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.get("/export")
def export_cases(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    settings = get_settings(db)
    if not settings.collection_enabled or not settings.support_export_enabled:
        raise HTTPException(status_code=403, detail="Support-Export wurde nicht freigegeben")
    purge_expired_cases(db, settings.retention_days)
    db.commit()
    cases = db.query(ChatFeedbackDiagnosticCase).order_by(ChatFeedbackDiagnosticCase.created_at.desc()).all()
    return JSONResponse(
        content={"generated_locally": True, "entries": [_serialize_case(case) for case in cases]},
        headers={"Content-Disposition": 'attachment; filename="doctus-chat-feedback-diagnostics.json"'},
    )
