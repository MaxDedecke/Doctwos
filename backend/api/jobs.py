"""Globales Job-Center (NF-014).

Fasst Quellen-Syncs, Link-Builder- und Diagnose-Läufe in eine einheitliche,
sichtbarkeitsgeschützte Liste zusammen. Fehlgeschlagene Jobs werden beim
Wiederaufnehmen nicht überschrieben: Run-basierte Jobs erhalten einen neuen Run,
damit die Fehlerhistorie erhalten bleibt.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from core.config import UPLOADS_DIR, celery_app
from core.db_setup import get_db
from core.projects import get_visible_project_ids
from core.teams import get_visible_team_ids, is_admin, require_admin
from core.tracing import get_trace_id
from models.database import DiagnosticsRun, JobCenterDismissal, KnowledgeSource, LinkBuilderRun, User
from services.job_control import revoke_tracked_task, send_tracked_task

router = APIRouter(prefix="/jobs", tags=["jobs"])
ACTIVE = {"pending", "running", "syncing", "parsing"}
TERMINAL = {"completed", "failed", "cancelled"}
SUPPORTED_SOURCE_TYPES = {"confluence", "jira", "folderwatch", "webdav", "git", "local"}


def _iso(value):
    return value.isoformat() if value else None


def _source_can_start(source: KnowledgeSource, admin: bool, status: str) -> bool:
    if not admin or status != "failed":
        return False
    source_type = (source.type or "").lower()
    if source_type != "local":
        return source_type in SUPPORTED_SOURCE_TYPES
    path_name = source.spaces.get("path") if isinstance(source.spaces, dict) else None
    return bool(path_name and os.path.isfile(os.path.join(UPLOADS_DIR, path_name)))


def _source_job(source: KnowledgeSource, admin: bool = False) -> dict:
    status = "running" if source.sync_status in {"syncing", "parsing"} else (source.sync_status or "pending")
    if status == "error":
        status = "failed"
    return {
        "key": f"source:{source.id}", "kind": "source", "id": source.id,
        "label": source.name, "status": status, "progress": source.progress or 0,
        "progress_message": source.progress_message, "error_message": source.last_error_detail or source.last_error,
        "created_at": _iso(source.parse_started_at or source.created_at),
        "finished_at": _iso(source.parse_finished_at), "can_resume": status == "failed",
        "can_start": _source_can_start(source, admin, status),
        "can_delete": admin and status in TERMINAL,
        "can_stop": admin and status in ACTIVE,
    }


def _run_job(run: LinkBuilderRun, admin: bool = False) -> dict:
    label = "Entity-Verknüpfungen" if run.task_type == "entity_links" else "Wissens-Verknüpfungen"
    return {
        "key": f"link_builder:{run.id}", "kind": "link_builder", "id": run.id,
        "label": label, "status": run.status, "progress": None,
        "progress_message": run.progress_message, "error_message": run.error_message,
        "created_at": _iso(run.created_at), "finished_at": _iso(run.finished_at),
        "can_resume": run.status == "failed", "can_start": admin and run.status == "failed",
        "can_delete": admin and run.status in TERMINAL,
        "can_stop": admin and run.status in ACTIVE,
    }


def _diagnostics_job(run: DiagnosticsRun, admin: bool = False) -> dict:
    return {
        "key": f"diagnostics:{run.id}", "kind": "diagnostics", "id": run.id,
        "label": "Diagnosepaket", "status": run.status, "progress": None,
        "progress_message": run.progress_message, "error_message": run.error_message,
        "created_at": _iso(run.created_at), "finished_at": _iso(run.finished_at),
        "can_resume": run.status == "failed", "can_start": admin and run.status == "failed",
        "can_delete": admin and run.status in TERMINAL,
        "can_stop": admin and run.status in ACTIVE,
    }


@router.get("")
def list_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project_ids = get_visible_project_ids(user, db)
    team_ids = get_visible_team_ids(user, db)

    source_query = db.query(KnowledgeSource)
    if team_ids is not None:
        source_query = source_query.filter(KnowledgeSource.team_id.in_(team_ids))
    if project_ids is not None:
        source_query = source_query.filter(or_(KnowledgeSource.project_id.is_(None), KnowledgeSource.project_id.in_(project_ids)))

    run_query = db.query(LinkBuilderRun)
    admin = is_admin(user)
    if not admin:
        run_query = run_query.filter(LinkBuilderRun.project_id.in_(project_ids or []))

    jobs = [_source_job(row, admin) for row in source_query.all()]
    jobs += [_run_job(row, admin) for row in run_query.all()]
    if admin:
        jobs += [_diagnostics_job(row, admin) for row in db.query(DiagnosticsRun).all()]
    dismissed = {
        (row.kind, row.job_id)
        for row in db.query(JobCenterDismissal).all()
    }
    jobs = [job for job in jobs if (job["kind"], job["id"]) not in dismissed]
    jobs.sort(key=lambda item: item["created_at"] or "", reverse=True)
    return {"active_count": sum(job["status"] in ACTIVE for job in jobs), "jobs": jobs}


def _queue_source(source: KnowledgeSource, db: Session) -> dict:
    source_type = (source.type or "").lower()
    file_path = None
    if source_type == "local":
        path_name = source.spaces.get("path") if isinstance(source.spaces, dict) else None
        file_path = os.path.join(UPLOADS_DIR, path_name) if path_name else None
        if not file_path or not os.path.isfile(file_path):
            raise HTTPException(409, "Die hochgeladene Datei ist nicht mehr vorhanden")

    source.sync_status = "pending"
    source.progress = 0
    source.progress_message = "In Warteschlange…"
    source.last_error = source.last_error_detail = None
    source.parse_finished_at = None
    db.query(JobCenterDismissal).filter(
        JobCenterDismissal.kind == "source",
        JobCenterDismissal.job_id == source.id,
    ).delete(synchronize_session=False)
    db.commit()
    if source_type == "local":
        send_tracked_task(db, source, "process_local_document", [source.id, file_path], {"trace_id": get_trace_id()})
    else:
        send_tracked_task(db, source, "process_knowledge_source", [source.id], {"trace_id": get_trace_id()})
    return {"message": "Job gestartet", "key": f"source:{source.id}"}


def _queue_link_builder(previous: LinkBuilderRun, db: Session) -> dict:
    run = LinkBuilderRun(task_type=previous.task_type, project_id=previous.project_id, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)
    task = "compute_entity_links" if run.task_type == "entity_links" else "compute_knowledge_links"
    args = [run.id, run.project_id] if run.task_type == "entity_links" else [run.id]
    send_tracked_task(db, run, task, args, {"trace_id": get_trace_id()})
    return {"message": "Job gestartet", "key": f"link_builder:{run.id}"}


def _queue_diagnostics(user: User, db: Session) -> dict:
    run = DiagnosticsRun(status="pending", triggered_by_user_id=user.id)
    db.add(run)
    db.commit()
    db.refresh(run)
    send_tracked_task(db, run, "generate_diagnostics_bundle", [run.id], {"trace_id": get_trace_id()})
    return {"message": "Job gestartet", "key": f"diagnostics:{run.id}"}


@router.post("/{kind}/{job_id}/start", dependencies=[Depends(require_admin)])
def start_job(kind: str, job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Start a new execution while retaining the previous execution record."""
    if kind == "source":
        source = db.query(KnowledgeSource).with_for_update().filter(KnowledgeSource.id == job_id).first()
        if not source:
            raise HTTPException(404, "Job nicht gefunden")
        status = "running" if source.sync_status in {"syncing", "parsing"} else (source.sync_status or "pending")
        if status == "error":
            status = "failed"
        if status in ACTIVE:
            raise HTTPException(409, "Job läuft bereits")
        if status != "failed":
            raise HTTPException(409, "Nur fehlgeschlagene Jobs können neu angestoßen werden")
        if not _source_can_start(source, True, status):
            raise HTTPException(409, "Für diesen Quelltyp gibt es keinen verarbeitbaren Job")
        return _queue_source(source, db)

    if kind == "link_builder":
        previous = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == job_id).first()
        if not previous:
            raise HTTPException(404, "Job nicht gefunden")
        if previous.task_type not in {"entity_links", "knowledge_links"}:
            raise HTTPException(409, "Unbekannter Jobtyp")
        if previous.status in ACTIVE:
            raise HTTPException(409, "Job läuft bereits")
        if previous.status != "failed":
            raise HTTPException(409, "Nur fehlgeschlagene Jobs können neu angestoßen werden")
        return _queue_link_builder(previous, db)

    if kind == "diagnostics":
        previous = db.query(DiagnosticsRun).filter(DiagnosticsRun.id == job_id).first()
        if not previous:
            raise HTTPException(404, "Job nicht gefunden")
        if previous.status in ACTIVE:
            raise HTTPException(409, "Job läuft bereits")
        if previous.status != "failed":
            raise HTTPException(409, "Nur fehlgeschlagene Jobs können neu angestoßen werden")
        return _queue_diagnostics(user, db)

    raise HTTPException(404, "Job nicht gefunden")


@router.delete("/{kind}/{job_id}", dependencies=[Depends(require_admin)])
def delete_job(kind: str, job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Dismiss a completed job while retaining the underlying execution record."""
    if kind == "source":
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == job_id).first()
        status = "running" if source and source.sync_status in {"syncing", "parsing"} else (source.sync_status if source else None)
        if status == "error":
            status = "failed"
        if not source:
            raise HTTPException(404, "Job nicht gefunden")
    elif kind == "link_builder":
        run = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == job_id).first()
        status = run.status if run else None
        if not run:
            raise HTTPException(404, "Job nicht gefunden")
    elif kind == "diagnostics":
        run = db.query(DiagnosticsRun).filter(DiagnosticsRun.id == job_id).first()
        status = run.status if run else None
        if not run:
            raise HTTPException(404, "Job nicht gefunden")
    else:
        raise HTTPException(404, "Job nicht gefunden")

    if status in ACTIVE:
        raise HTTPException(409, "Laufende Jobs können nicht entfernt werden")
    if status not in TERMINAL:
        raise HTTPException(409, "Nur abgeschlossene, fehlgeschlagene oder abgebrochene Jobs können entfernt werden")

    dismissal = db.query(JobCenterDismissal).filter(
        JobCenterDismissal.kind == kind,
        JobCenterDismissal.job_id == job_id,
    ).first()
    if not dismissal:
        db.add(JobCenterDismissal(kind=kind, job_id=job_id, dismissed_by_user_id=user.id))
        db.commit()
    return {"message": "Job aus dem Job-Center entfernt", "key": f"{kind}:{job_id}"}


@router.post("/{kind}/{job_id}/stop", dependencies=[Depends(require_admin)])
def stop_job(kind: str, job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Cancel an active job and revoke its Celery task when an id is available."""
    task_id = None
    if kind == "source":
        record = db.query(KnowledgeSource).filter(KnowledgeSource.id == job_id).first()
        if not record:
            raise HTTPException(404, "Job nicht gefunden")
        status = "running" if record.sync_status in {"syncing", "parsing"} else (record.sync_status or "pending")
        if status == "error":
            status = "failed"
        if status not in ACTIVE:
            raise HTTPException(409, "Nur laufende Jobs können abgebrochen werden")
        task_id = record.celery_task_id
        record.sync_status = "cancelled"
        record.progress_message = "Vom Administrator abgebrochen"
        record.last_error = record.last_error_detail = "Job wurde vom Administrator abgebrochen"
        record.parse_finished_at = datetime.now(timezone.utc)
    elif kind == "link_builder":
        record = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == job_id).first()
        if not record:
            raise HTTPException(404, "Job nicht gefunden")
        if record.status not in ACTIVE:
            raise HTTPException(409, "Nur laufende Jobs können abgebrochen werden")
        task_id = record.celery_task_id
        record.status = "cancelled"
        record.progress_message = "Vom Administrator abgebrochen"
        record.error_message = "Job wurde vom Administrator abgebrochen"
        record.finished_at = datetime.now(timezone.utc)
    elif kind == "diagnostics":
        record = db.query(DiagnosticsRun).filter(DiagnosticsRun.id == job_id).first()
        if not record:
            raise HTTPException(404, "Job nicht gefunden")
        if record.status not in ACTIVE:
            raise HTTPException(409, "Nur laufende Jobs können abgebrochen werden")
        task_id = record.celery_task_id
        record.status = "cancelled"
        record.progress_message = "Vom Administrator abgebrochen"
        record.error_message = "Job wurde vom Administrator abgebrochen"
        record.finished_at = datetime.now(timezone.utc)
    else:
        raise HTTPException(404, "Job nicht gefunden")

    db.commit()
    revoke_tracked_task(task_id)
    return {"message": "Job abgebrochen", "key": f"{kind}:{job_id}"}


@router.post("/{kind}/{job_id}/resume")
def resume_job(kind: str, job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    trace = {"trace_id": get_trace_id()}
    if kind == "source":
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == job_id).first()
        if not source:
            raise HTTPException(404, "Job nicht gefunden")
        team_ids = get_visible_team_ids(user, db)
        project_ids = get_visible_project_ids(user, db)
        if (team_ids is not None and source.team_id not in team_ids) or (
            project_ids is not None and source.project_id is not None and source.project_id not in project_ids
        ):
            raise HTTPException(403, "Kein Zugriff auf diesen Job")
        if source.sync_status != "error":
            raise HTTPException(409, "Nur fehlgeschlagene Jobs können wiederaufgenommen werden")
        source.sync_status, source.progress, source.progress_message = "pending", 0, "Wiederaufnahme in Warteschlange…"
        source.last_error = source.last_error_detail = None
        source.parse_finished_at = None
        db.commit()
        send_tracked_task(db, source, "process_knowledge_source", [source.id])
        return {"message": "Job wiederaufgenommen", "key": f"source:{source.id}"}

    if kind == "link_builder":
        previous = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == job_id).first()
        if not previous:
            raise HTTPException(404, "Job nicht gefunden")
        if previous.status != "failed":
            raise HTTPException(409, "Nur fehlgeschlagene Jobs können wiederaufgenommen werden")
        project_ids = get_visible_project_ids(user, db)
        if previous.project_id is None and not is_admin(user):
            raise HTTPException(403, "Kein Zugriff auf diesen Job")
        if project_ids is not None and previous.project_id not in project_ids:
            raise HTTPException(403, "Kein Zugriff auf diesen Job")
        run = LinkBuilderRun(task_type=previous.task_type, project_id=previous.project_id, status="pending")
        db.add(run)
        db.commit()
        db.refresh(run)
        task = "compute_entity_links" if run.task_type == "entity_links" else "compute_knowledge_links"
        args = [run.id, run.project_id] if run.task_type == "entity_links" else [run.id]
        send_tracked_task(db, run, task, args, trace)
        return {"message": "Job wiederaufgenommen", "key": f"link_builder:{run.id}"}

    if kind == "diagnostics" and is_admin(user):
        previous = db.query(DiagnosticsRun).filter(DiagnosticsRun.id == job_id).first()
        if not previous:
            raise HTTPException(404, "Job nicht gefunden")
        if previous.status != "failed":
            raise HTTPException(409, "Nur fehlgeschlagene Jobs können wiederaufgenommen werden")
        run = DiagnosticsRun(status="pending", triggered_by_user_id=user.id)
        db.add(run)
        db.commit()
        db.refresh(run)
        send_tracked_task(db, run, "generate_diagnostics_bundle", [run.id], trace)
        return {"message": "Job wiederaufgenommen", "key": f"diagnostics:{run.id}"}

    raise HTTPException(404, "Job nicht gefunden")
