"""Shared Celery dispatch and cancellation helpers for visible background jobs."""

import logging
from typing import Any

from core.config import celery_app

logger = logging.getLogger(__name__)


def send_tracked_task(db, record: Any, task_name: str, args: list[Any], kwargs: dict[str, Any] | None = None):
    """Dispatch a task and retain its broker identifier on the visible job record."""
    if kwargs is None:
        result = celery_app.send_task(task_name, args=args)
    else:
        result = celery_app.send_task(task_name, args=args, kwargs=kwargs)
    task_id = getattr(result, "id", None)
    if task_id:
        record.celery_task_id = task_id
        db.commit()
    return result


def revoke_tracked_task(task_id: str | None) -> None:
    """Revoke a task and terminate an already-running worker child process."""
    if task_id:
        try:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        except Exception:
            # The database state is already cancelled; a broker outage must not
            # turn a successful user action into a misleading HTTP error.
            logger.exception("Could not revoke Celery task %s", task_id)
