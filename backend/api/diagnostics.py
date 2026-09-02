"""
backend/api/diagnostics.py
===========================
Diagnose-Bundle: Admin-getriggerte Alternative zu scripts/generate_diagnostics.py
für Support-Fälle ohne Shell-Zugriff (Settings > Logs Button im Frontend).

Endpunkte:
    POST /diagnostics/generate              — Bundle-Erzeugung anstoßen (Celery)
    GET  /diagnostics/runs                  — Verlauf aller Bundle-Läufe
    GET  /diagnostics/runs/{run_id}/download — Fertiges Bundle herunterladen

Admin-Gate: der gesamte Router ist in main.py mit
dependencies=[Depends(require_admin)] eingebunden (gleiches Muster wie
topics.router) — ein Diagnose-Bundle enthält DB-Auszüge und Logs, kein
Endpunkt hier darf für normale Nutzer erreichbar sein.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config import celery_app
from core.tracing import get_trace_id
from core.db_setup import get_db
from core.auth_dependency import get_current_user
from models.database import DiagnosticsRun, User
from services.job_control import send_tracked_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

# Separate, deliberately unauthenticated router: a frontend crash can happen
# before login (or because login itself is broken), so the opt-in "send error
# report" button in app/error.tsx must be reachable without a session. Kept
# out of `router` above, which main.py gates behind require_admin.
public_router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class ClientErrorReport(BaseModel):
    message: str
    stack: str | None = None
    digest: str | None = None
    url: str | None = None


@public_router.post("/client-error")
def report_client_error(report: ClientErrorReport):
    """
    Opt-in only — the frontend error boundary never calls this automatically,
    only when the user clicks "Send error report". No persistence beyond the
    log line: this is meant to make a crash visible in the same place every
    other service's logs land (see the shared /var/log/doctus mount), not to
    build a client-side crash database.
    """
    logger.error(
        "[ClientError] %s | url=%s | digest=%s | stack=%s",
        report.message[:1000],
        (report.url or "")[:500],
        report.digest or "-",
        (report.stack or "")[:4000],
    )
    return {"message": "Error report received"}


def _serialize_run(run: DiagnosticsRun) -> dict:
    return {
        "id": run.id,
        "status": run.status,
        "progress_message": run.progress_message,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "triggered_by_user_id": run.triggered_by_user_id,
    }


@router.post("/generate")
def trigger_diagnostics_bundle(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = DiagnosticsRun(status="pending", triggered_by_user_id=user.id)
    db.add(run)
    db.commit()
    db.refresh(run)

    send_tracked_task(db, run, "generate_diagnostics_bundle", [run.id], {"trace_id": get_trace_id()})
    return {"message": "Diagnostics bundle generation started", "run_id": run.id}


@router.get("/runs")
def list_diagnostics_runs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Verlauf, neueste zuerst — inklusive fehlgeschlagener Läufe, damit ein
    Absturz hier sichtbar bleibt statt spurlos im Hintergrund zu verschwinden."""
    runs = db.query(DiagnosticsRun).order_by(DiagnosticsRun.created_at.desc()).limit(50).all()
    return [_serialize_run(r) for r in runs]


@router.get("/runs/{run_id}/download")
def download_diagnostics_bundle(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = db.query(DiagnosticsRun).filter(DiagnosticsRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Diagnostics run nicht gefunden")
    if run.status != "completed" or not run.bundle_path:
        raise HTTPException(status_code=409, detail=f"Bundle ist noch nicht fertig (Status: {run.status})")
    if not os.path.isfile(run.bundle_path):
        raise HTTPException(status_code=410, detail="Bundle-Datei nicht mehr vorhanden")

    return FileResponse(
        run.bundle_path,
        media_type="application/gzip",
        filename=os.path.basename(run.bundle_path),
    )
