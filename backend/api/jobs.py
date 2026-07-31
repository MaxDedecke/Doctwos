"""Globales Job-Center (NF-014).

Fasst Quellen-Syncs, Link-Builder- und Diagnose-Läufe in eine einheitliche,
sichtbarkeitsgeschützte Liste zusammen. Fehlgeschlagene Jobs werden beim
Wiederaufnehmen nicht überschrieben: Run-basierte Jobs erhalten einen neuen Run,
damit die Fehlerhistorie erhalten bleibt.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from core.config import celery_app
from core.db_setup import get_db
from core.projects import get_visible_project_ids
from core.teams import get_visible_team_ids, is_admin
from core.tracing import get_trace_id
from models.database import DiagnosticsRun, KnowledgeSource, LinkBuilderRun, User

router = APIRouter(prefix="/jobs", tags=["jobs"])
ACTIVE = {"pending", "running", "syncing", "parsing"}


def _iso(value):
    return value.isoformat() if value else None


def _source_job(source: KnowledgeSource) -> dict:
    status = "running" if source.sync_status in {"syncing", "parsing"} else source.sync_status
    if status == "error":
        status = "failed"
    return {
        "key": f"source:{source.id}", "kind": "source", "id": source.id,
        "label": source.name, "status": status, "progress": source.progress or 0,
        "progress_message": source.progress_message, "error_message": source.last_error_detail or source.last_error,
        "created_at": _iso(source.parse_started_at or source.created_at),
        "finished_at": _iso(source.parse_finished_at), "can_resume": status == "failed",
    }


def _run_job(run: LinkBuilderRun) -> dict:
    label = "Entity-Verknüpfungen" if run.task_type == "entity_links" else "Wissens-Verknüpfungen"
    return {
        "key": f"link_builder:{run.id}", "kind": "link_builder", "id": run.id,
        "label": label, "status": run.status, "progress": None,
        "progress_message": run.progress_message, "error_message": run.error_message,
        "created_at": _iso(run.created_at), "finished_at": _iso(run.finished_at),
        "can_resume": run.status == "failed",
    }


def _diagnostics_job(run: DiagnosticsRun) -> dict:
    return {
        "key": f"diagnostics:{run.id}", "kind": "diagnostics", "id": run.id,
        "label": "Diagnosepaket", "status": run.status, "progress": None,
        "progress_message": run.progress_message, "error_message": run.error_message,
        "created_at": _iso(run.created_at), "finished_at": _iso(run.finished_at),
        "can_resume": run.status == "failed",
    }


@router.get("")
def list_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project_ids = get_visible_project_ids(user, db)
    team_ids = get_visible_team_ids(user, db)

    source_query = db.query(KnowledgeSource).filter(
        KnowledgeSource.sync_status.in_(("pending", "syncing", "parsing", "error"))
    )
    if team_ids is not None:
        source_query = source_query.filter(KnowledgeSource.team_id.in_(team_ids))
    if project_ids is not None:
        source_query = source_query.filter(or_(KnowledgeSource.project_id.is_(None), KnowledgeSource.project_id.in_(project_ids)))

    run_query = db.query(LinkBuilderRun).filter(LinkBuilderRun.status.in_(("pending", "running", "failed")))
    if not is_admin(user):
        run_query = run_query.filter(LinkBuilderRun.project_id.in_(project_ids or []))

    jobs = [_source_job(row) for row in source_query.all()]
    jobs += [_run_job(row) for row in run_query.all()]
    if is_admin(user):
        jobs += [_diagnostics_job(row) for row in db.query(DiagnosticsRun).filter(
            DiagnosticsRun.status.in_(("pending", "running", "failed"))
        ).all()]
    jobs.sort(key=lambda item: item["created_at"] or "", reverse=True)
    return {"active_count": sum(job["status"] in ACTIVE for job in jobs), "jobs": jobs}


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
        celery_app.send_task("process_knowledge_source", args=[source.id])
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
        celery_app.send_task(task, args=args, kwargs=trace)
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
        celery_app.send_task("generate_diagnostics_bundle", args=[run.id], kwargs=trace)
        return {"message": "Job wiederaufgenommen", "key": f"diagnostics:{run.id}"}

    raise HTTPException(404, "Job nicht gefunden")
