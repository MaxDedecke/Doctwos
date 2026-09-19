"""Reconciliation and scope-level deduplication for knowledge-link runs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.database import LinkBuilderRun, Project
from services.job_control import revoke_tracked_task


DISPATCH_TIMEOUT_SECONDS = 120
PENDING_TIMEOUT_SECONDS = 1800
ACTIVE_STATUSES = ("pending", "running")


def scope_project_id(project_id: int | None, scope: dict | None) -> int | None:
    """Resolve project ownership for old runs whose FK was nulled on deletion."""
    value = project_id
    if value is None and isinstance(scope, dict):
        value = scope.get("project_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _scope_key(project_id: int | None, scope: dict | None) -> tuple[int | None, str] | None:
    if not isinstance(scope, dict):
        scope = {}
    resolved_project_id = scope_project_id(project_id, scope)
    if resolved_project_id is None and not scope:
        return None

    normalized = dict(scope)
    # Queue metadata is operational, not part of the requested analysis scope.
    normalized.pop("queue", None)
    normalized.pop("confirmed", None)
    if resolved_project_id is not None:
        normalized["project_id"] = resolved_project_id
    source_ids = normalized.get("source_ids")
    if isinstance(source_ids, list):
        try:
            normalized["source_ids"] = sorted({int(source_id) for source_id in source_ids})
        except (TypeError, ValueError):
            normalized["source_ids"] = sorted(source_ids, key=str)
    return resolved_project_id, json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def lock_project_scope(db: Session, project_id: int | None, scope: dict | None) -> int | None:
    """Serialize run creation for a project on databases supporting row locks."""
    resolved_project_id = scope_project_id(project_id, scope)
    if resolved_project_id is not None:
        db.query(Project.id).filter(Project.id == resolved_project_id).with_for_update().first()
    return resolved_project_id


def find_active_knowledge_link_run(
    db: Session, project_id: int | None, scope: dict | None
) -> LinkBuilderRun | None:
    """Return the oldest active run for the same project and source scope."""
    wanted_key = _scope_key(project_id, scope)
    if wanted_key is None:
        return None

    query = db.query(LinkBuilderRun).filter(
        LinkBuilderRun.task_type == "knowledge_links",
        LinkBuilderRun.status.in_(ACTIVE_STATUSES),
    )
    resolved_project_id = wanted_key[0]
    if resolved_project_id is None:
        query = query.filter(LinkBuilderRun.project_id.is_(None))
    else:
        # Include legacy rows with a nulled FK; the scope key filters them by
        # their original project before they can be returned as a duplicate.
        query = query.filter(
            or_(
                LinkBuilderRun.project_id == resolved_project_id,
                LinkBuilderRun.project_id.is_(None),
            )
        )
    rows = query.order_by(LinkBuilderRun.id.asc()).all()
    return next(
        (row for row in rows if _scope_key(row.project_id, row.scope_json) == wanted_key),
        None,
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _finish_run(run: LinkBuilderRun, status: str, message: str, now: datetime) -> None:
    run.status = status
    run.progress_message = message
    run.error_message = message
    run.finished_at = now


def reconcile_knowledge_link_runs(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Cancel orphan/duplicate runs and fail pending runs that never started.

    Called by the Job Center and run-history endpoints. Per-project row locks
    use the same order as enqueue operations, so reconciliation cannot race a
    second run into the same scope on PostgreSQL.
    """
    now = _as_utc(now or datetime.now(timezone.utc))
    initial_rows = (
        db.query(LinkBuilderRun)
        .filter(
            LinkBuilderRun.task_type == "knowledge_links",
            LinkBuilderRun.status.in_(ACTIVE_STATUSES),
        )
        .all()
    )
    project_ids = sorted(
        {
            resolved_id
            for row in initial_rows
            if (resolved_id := scope_project_id(row.project_id, row.scope_json)) is not None
        }
    )
    if project_ids:
        db.query(Project.id).filter(Project.id.in_(project_ids)).order_by(
            Project.id
        ).with_for_update().all()

    rows = (
        db.query(LinkBuilderRun)
        .filter(
            LinkBuilderRun.task_type == "knowledge_links",
            LinkBuilderRun.status.in_(ACTIVE_STATUSES),
        )
        .order_by(LinkBuilderRun.id.asc())
        .with_for_update()
        .all()
    )
    existing_project_ids = (
        {row[0] for row in db.query(Project.id).filter(Project.id.in_(project_ids)).all()}
        if project_ids
        else set()
    )

    counts = {"orphaned": 0, "stuck": 0, "duplicates": 0}
    task_ids_to_revoke: set[str] = set()
    active_by_scope: dict[tuple[int | None, str], LinkBuilderRun] = {}
    for run in rows:
        resolved_project_id = scope_project_id(run.project_id, run.scope_json)
        if run.project_id is None and resolved_project_id is not None:
            if resolved_project_id not in existing_project_ids:
                _finish_run(
                    run,
                    "cancelled",
                    f"Verwaister Lauf: Projekt {resolved_project_id} existiert nicht mehr.",
                    now,
                )
                if run.celery_task_id:
                    task_ids_to_revoke.add(run.celery_task_id)
                counts["orphaned"] += 1
                continue

        created_at = _as_utc(run.created_at)
        age = now - created_at if created_at is not None else timedelta.max
        missing_task_id_timed_out = not run.celery_task_id and age >= timedelta(
            seconds=DISPATCH_TIMEOUT_SECONDS
        )
        pending_timed_out = run.status == "pending" and age >= timedelta(
            seconds=PENDING_TIMEOUT_SECONDS
        )
        if missing_task_id_timed_out or pending_timed_out:
            reason = (
                "Keine Celery-Task-ID innerhalb des Dispatch-Zeitlimits gespeichert."
                if missing_task_id_timed_out
                else "Der Lauf blieb länger als das Pending-Zeitlimit in der Warteschlange."
            )
            _finish_run(run, "failed", reason, now)
            if run.celery_task_id:
                task_ids_to_revoke.add(run.celery_task_id)
            counts["stuck"] += 1
            continue

        key = _scope_key(run.project_id, run.scope_json)
        if key is None:
            continue
        previous = active_by_scope.get(key)
        if previous is None:
            active_by_scope[key] = run
            continue
        _finish_run(
            run,
            "cancelled",
            f"Doppelter aktiver Lauf; Run {previous.id} bleibt für diesen Scope erhalten.",
            now,
        )
        if run.celery_task_id:
            task_ids_to_revoke.add(run.celery_task_id)
        counts["duplicates"] += 1

    if any(counts.values()):
        db.commit()
    for task_id in task_ids_to_revoke:
        revoke_tracked_task(task_id)
    return counts
