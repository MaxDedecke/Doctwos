"""Assigned insight tasks, bounded search, evidence selection and a personal inbox."""

from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session, defer
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_project_visible, get_project_role
from doctus_models.database import (
    Insight,
    InsightNotification,
    CodeEntity,
    DocumentChunk,
    CIBuildRun,
    Project,
)
from doctus_models.insight_versions import version_state
from doctus_models.insight_evidence import project_chunk_scope
from doctus_models.insight_workflow import notify_insight, touched
from services.insight_queue import (
    worklist_query,
    order_worklist,
    assignment_candidates,
    valid_assignee,
)
from services.insight_records import serialize_insight
from services.insight_maintenance import finish_notifications


def assert_work_project(project_id, user, db):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/projects", tags=["insight-worklist"], dependencies=[Depends(no_store)])
STATUS = Literal["draft", "verified", "outdated", "rejected"]


@router.get("/{project_id}/insight-worklist")
def worklist(
    project_id: int,
    q: str = Query(default="", max_length=300),
    status: STATUS | None = None,
    mine: bool = False,
    unassigned: bool = False,
    reviewer: bool = False,
    needs_review: bool = False,
    priority: int | None = Query(default=None, ge=0, le=3),
    limit: int = Query(default=25, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100000),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    assert_work_project(project_id, user, db)
    query, rank = worklist_query(
        db,
        project_id,
        user,
        q=q.strip(),
        status=status,
        mine=mine,
        unassigned=unassigned,
        reviewer=reviewer,
        needs_review=needs_review,
        priority=priority,
    )
    total = query.count()
    rows = (
        order_worklist(query, rank)
        .options(
            defer(Insight.content),
            defer(Insight.review_history),
            defer(Insight.workflow_history),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = []
    for row in rows:
        state = version_state(db, row)
        items.append(
            {
                **{
                    key: getattr(row, key)
                    for key in (
                        "id",
                        "title",
                        "status",
                        "revision",
                        "owner_id",
                        "reviewer_id",
                        "priority",
                        "work_revision",
                        "created_by_id",
                    )
                },
                "due_at": row.due_at.isoformat() if row.due_at else None,
                "version_state": state,
                "evidence_count": len(row.evidence_json or []),
                "needs_review": row.status in {"draft", "outdated"}
                or (row.status == "verified" and state not in {"current", "project"}),
            }
        )
    counts = dict(
        db.query(Insight.status, func.count(Insight.id))
        .filter(
            Insight.project_id == project_id,
        )
        .group_by(Insight.status)
        .all()
    )
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
        "counts": counts,
    }


@router.get("/{project_id}/insight-assignees")
def assignees(project_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    assert_work_project(project_id, user, db)
    rows = assignment_candidates(db, project_id)
    items = [
        {
            "id": u.id,
            "name": u.name or u.username,
            "can_review": role == "admin" or u.role == "superuser",
        }
        for u, role in rows[:500]
    ]
    if user.role == "superuser" and user.id not in {i["id"] for i in items}:
        items.append({"id": user.id, "name": user.name or user.username, "can_review": True})
    return {
        "items": items,
        "truncated": len(rows) > 500,
        "can_manage": get_project_role(project_id, user, db) == "admin",
    }


class Assignment(BaseModel):
    expected_revision: int = Field(ge=1)
    expected_work_revision: int = Field(ge=1)
    owner_id: int | None = Field(default=None, ge=1)
    reviewer_id: int | None = Field(default=None, ge=1)
    priority: int = Field(default=1, ge=0, le=3)
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def aware_due(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("Termin benötigt eine Zeitzone")
        return value


@router.patch("/{project_id}/insights/{insight_id}/assignment")
def assign(
    project_id: int,
    insight_id: int,
    body: Assignment,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    assert_work_project(project_id, user, db)
    can_manage = get_project_role(project_id, user, db) == "admin"
    row = (
        db.query(Insight).filter_by(id=insight_id, project_id=project_id).with_for_update().first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Erkenntnis nicht gefunden")
    if row.revision != body.expected_revision or row.work_revision != body.expected_work_revision:
        raise HTTPException(status_code=409, detail="Erkenntnis oder Zuständigkeit wurde geändert")
    values = {
        field: getattr(body, field) if field in body.model_fields_set else getattr(row, field)
        for field in ("owner_id", "reviewer_id", "priority", "due_at")
    }
    if not can_manage and (
        user.id != row.owner_id
        and not (row.owner_id is None and user.id == row.created_by_id)
        or any(values[field] != getattr(row, field) for field in ("owner_id", "priority", "due_at"))
    ):
        raise HTTPException(
            status_code=403,
            detail="Verantwortliche dürfen eine Prüfung anfordern; weitere Zuweisungen benötigen Projekt-Admins",
        )
    if not valid_assignee(db, project_id, values["owner_id"]) or not valid_assignee(
        db, project_id, values["reviewer_id"], reviewer=True
    ):
        raise HTTPException(
            status_code=422,
            detail="Verantwortliche müssen aktive Projektmitglieder sein; Prüfer benötigen Freigaberechte",
        )
    if values["reviewer_id"] == row.created_by_id and user.role != "superuser":
        raise HTTPException(status_code=422, detail="Die Prüfung benötigt eine andere Person")
    if all(getattr(row, field) == value for field, value in values.items()):
        return serialize_insight(row, db)
    row.workflow_history = [
        *(row.workflow_history or []),
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "by": user.id,
            "work_revision": row.work_revision,
            "owner_id": row.owner_id,
            "reviewer_id": row.reviewer_id,
            "priority": row.priority,
            "due_at": row.due_at.isoformat() if row.due_at else None,
        },
    ]
    if row.owner_id != values["owner_id"] or row.reviewer_id != values["reviewer_id"]:
        finish_notifications(db, row)
    row.owner_id, row.reviewer_id = values["owner_id"], values["reviewer_id"]
    row.priority, row.due_at = values["priority"], values["due_at"]
    row.work_revision += 1
    touched(row)
    notify_insight(db, row, "assigned", actor_id=user.id, recipients=[row.owner_id])
    notify_insight(db, row, "review_requested", actor_id=user.id, recipients=[row.reviewer_id])
    db.commit()
    return serialize_insight(row, db)


@router.get("/{project_id}/insight-notifications")
def inbox(
    project_id: int,
    unread_only: bool = True,
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    assert_work_project(project_id, user, db)
    query = db.query(InsightNotification).filter_by(project_id=project_id, user_id=user.id)
    count = query.filter(InsightNotification.read_at.is_(None)).count()
    if unread_only:
        query = query.filter(InsightNotification.read_at.is_(None))
    rows = query.order_by(InsightNotification.id.desc()).limit(limit + 1).all()
    titles = dict(
        db.query(Insight.id, Insight.title)
        .filter(Insight.id.in_([r.insight_id for r in rows[:limit]]))
        .all()
    )
    return {
        "unread_count": count,
        "has_more": len(rows) > limit,
        "items": [
            {
                "id": r.id,
                "insight_id": r.insight_id,
                "title": titles.get(r.insight_id),
                "kind": r.kind,
                "created_at": r.created_at.isoformat(),
                "read_at": r.read_at.isoformat() if r.read_at else None,
            }
            for r in rows[:limit]
        ],
    }


@router.post("/{project_id}/insight-notifications/read")
def read_notifications(
    project_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    assert_work_project(project_id, user, db)
    count = (
        db.query(InsightNotification)
        .filter_by(project_id=project_id, user_id=user.id)
        .filter(
            InsightNotification.read_at.is_(None),
        )
        .update({"read_at": datetime.now(timezone.utc)}, synchronize_session=False)
    )
    db.commit()
    return {"read": count}


@router.post("/{project_id}/insight-notifications/{notification_id}/read")
def read_notification(
    project_id: int,
    notification_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    assert_work_project(project_id, user, db)
    row = (
        db.query(InsightNotification)
        .filter_by(
            id=notification_id,
            project_id=project_id,
            user_id=user.id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Hinweis nicht gefunden")
    row.read_at = row.read_at or datetime.now(timezone.utc)
    db.commit()
    return {"read": 1}


@router.get("/{project_id}/insights/{insight_id}")
def detail(
    project_id: int, insight_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    assert_work_project(project_id, user, db)
    row = db.query(Insight).filter_by(id=insight_id, project_id=project_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Erkenntnis nicht gefunden")
    result = serialize_insight(row, db)
    result["history_truncated"] = (
        len(result["review_history"]) > 20 or len(result["workflow_history"]) > 20
    )
    result["review_history"] = result["review_history"][-20:]
    result["workflow_history"] = result["workflow_history"][-20:]
    return result


@router.get("/{project_id}/insight-evidence-options")
def evidence_options(
    project_id: int,
    q: str = Query(min_length=2, max_length=200),
    kind: Literal["code", "file", "insight", "ci"] = "code",
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    assert_work_project(project_id, user, db)
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    if kind == "code":
        rows = (
            db.query(CodeEntity)
            .filter(CodeEntity.project_id == project_id, CodeEntity.qualified_name.ilike(pattern))
            .order_by(CodeEntity.id)
            .limit(20)
            .all()
        )
        items = [
            {
                "label": f"{r.qualified_name} · {r.file_path}",
                "evidence": {
                    "entity_id": r.id,
                    "source_id": r.source_id,
                    "file": r.file_path,
                    "start_line": r.start_line,
                },
            }
            for r in rows
        ]
    elif kind == "file":
        rows = (
            db.query(DocumentChunk.source_id, DocumentChunk.file_path)
            .filter(project_chunk_scope(project_id), DocumentChunk.file_path.ilike(pattern))
            .distinct()
            .order_by(DocumentChunk.file_path)
            .limit(20)
            .all()
        )
        items = [
            {"label": f"{path} · #{sid}", "evidence": {"file": path, "source_id": sid}}
            for sid, path in rows
        ]
    elif kind == "insight":
        rows = (
            db.query(Insight.id, Insight.title, Insight.status)
            .filter(Insight.project_id == project_id, Insight.title.ilike(pattern))
            .order_by(Insight.id.desc())
            .limit(20)
            .all()
        )
        items = [
            {"label": f"#{r.id} · {r.title} · {r.status}", "evidence": {"insight_id": r.id}}
            for r in rows
        ]
    else:
        rows = (
            db.query(CIBuildRun)
            .filter(CIBuildRun.project_id == project_id, CIBuildRun.job_name.ilike(pattern))
            .order_by(CIBuildRun.id.desc())
            .limit(20)
            .all()
        )
        items = [
            {
                "label": f"{r.job_name} · {r.variant} · {r.commit[:12]}",
                "evidence": {
                    "ci_build_id": r.id,
                    "source_id": r.source_id,
                    "source_commit": r.commit,
                },
            }
            for r in rows
        ]
    return {"items": items, "truncated": len(items) == 20}


class ApprovalItem(BaseModel):
    id: int = Field(ge=1)
    expected_revision: int = Field(ge=1)
    expected_versions: list[dict]


class BatchApproval(BaseModel):
    confirm: bool
    items: list[ApprovalItem] = Field(min_length=1, max_length=20)


@router.post("/{project_id}/insight-batch-approval")
def batch_approval(
    project_id: int,
    body: BatchApproval,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from api.insights import verify_insight
    from api.schemas import InsightVerification

    assert_work_project(project_id, user, db)
    if not body.confirm:
        raise HTTPException(
            status_code=422, detail="Jede ausgewählte Erkenntnis ausdrücklich prüfen und bestätigen"
        )
    if get_project_role(project_id, user, db) != "admin":
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins dürfen freigeben")
    if len({i.id for i in body.items}) != len(body.items):
        raise HTTPException(
            status_code=422, detail="Erkenntnisse dürfen nicht doppelt ausgewählt werden"
        )
    results = []
    for item in body.items:
        try:
            value = verify_insight(
                project_id,
                item.id,
                InsightVerification(
                    confirm=True,
                    expected_revision=item.expected_revision,
                    expected_versions=item.expected_versions,
                ),
                db,
                user,
            )
            results.append({"id": item.id, "status": "verified", "revision": value["revision"]})
        except HTTPException as exc:
            db.rollback()
            results.append(
                {"id": item.id, "status": "error", "code": exc.status_code, "detail": exc.detail}
            )
    return {"items": results}
