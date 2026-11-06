"""Link-Läufe anlegen und in die Warteschlange stellen; gemeinsam für die Einzel-Endpunkte
(`/link-recommendations/compute`, `/knowledge-links/compute`) und die Analyse-Arbeitsfläche (`/link-runs`)."""

from __future__ import annotations

from sqlalchemy.orm import Session

import core.config as cfg
from core.tracing import get_trace_id
from doctus_models.database import LinkBuilderRun, Project, User
from services.job_control import send_tracked_task
from services.link_builder_runs import find_active_knowledge_link_run, reconcile_knowledge_link_runs


def had_full_run(db: Session, project_id: int) -> bool:
    """Ein abgeschlossener Entity-Lauf ohne Mengen; ein eingeschränkter Lauf ersetzt den Erstlauf nicht."""
    rows = db.query(LinkBuilderRun.scope_json).filter(
        LinkBuilderRun.project_id == project_id,
        LinkBuilderRun.task_type == "entity_links",
        LinkBuilderRun.status == "completed",
    )
    return any(not (scope or {}).get("sets") for (scope,) in rows)


def active_entity_link_run(db: Session, project_id: int) -> LinkBuilderRun | None:
    return (
        db.query(LinkBuilderRun)
        .filter(
            LinkBuilderRun.project_id == project_id,
            LinkBuilderRun.task_type == "entity_links",
            LinkBuilderRun.status.in_(["pending", "running"]),
        )
        .order_by(LinkBuilderRun.created_at.desc())
        .first()
    )


def queue_entity_link_run(
    db: Session,
    user: User,
    project_id: int,
    *,
    min_confidence: int | None,
    embedding_model: str | None,
    max_items: int,
    params: dict,
    sets: dict | None = None,
) -> dict:
    """Code↔Doku-Lauf. Je Projekt läuft höchstens einer (Redis-Sperre im Worker); ein aktiver wird zurückgegeben."""
    # O-315: Deduplizierung statt eines zweiten teuren Batch-Laufs.
    active = active_entity_link_run(db, project_id)
    if active is not None:
        return {
            "message": "Für dieses Projekt läuft bereits eine Link-Berechnung",
            "project_id": project_id,
            "run_id": active.id,
            "deduplicated": True,
        }
    model = embedding_model.strip() if embedding_model else None
    scope = {
        "project_id": project_id,
        "min_confidence": min_confidence,
        "embedding_model": model,
        "max_items": max_items,
        # O-183: Nur gesetzte Parameter; der Worker ergänzt Standardwerte und schreibt die wirksamen zurück.
        "params": params,
    }
    if sets:
        scope["sets"] = sets
    run = LinkBuilderRun(
        task_type="entity_links",
        project_id=project_id,
        status="pending",
        embedding_model=model,
        scope_json=scope,
        triggered_by_user_id=user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    send_tracked_task(
        db,
        run,
        "compute_entity_links",
        [run.id, project_id],
        {"trace_id": get_trace_id(), "min_confidence": min_confidence, "embedding_model": model},
    )
    return {"message": "Link computation started", "project_id": project_id, "run_id": run.id}


def queue_knowledge_link_run(
    db: Session,
    user: User,
    project_id: int,
    *,
    min_confidence: int | None,
    embedding_model: str | None,
    max_items: int,
    source_ids: list[int] | None = None,
    sets: dict | None = None,
) -> dict:
    """Dokument↔Dokument-Lauf über ``source_ids`` (ältere Form) oder Mengen; je Scope läuft höchstens einer."""
    # Stale Einträge vor der Duplikatprüfung bereinigen; die Projektzeilen-Sperre serialisiert parallele Starts.
    reconcile_knowledge_link_runs(db)
    db.query(Project).filter(Project.id == project_id).with_for_update().first()
    scope: dict = {
        "project_id": project_id,
        "queue": "global_link_runs",
        "confirmed": True,
        "max_items": max_items,
        "min_confidence": min_confidence,
    }
    if source_ids:
        scope["source_ids"] = sorted(set(source_ids))
    if sets:
        scope["sets"] = sets
    existing = find_active_knowledge_link_run(db, project_id, scope)
    if existing is not None:
        db.commit()
        return {
            "message": "Für diesen Scope läuft bereits ein Job",
            "run_id": existing.id,
            "scope": existing.scope_json,
            "deduplicated": True,
        }
    run = LinkBuilderRun(
        task_type="knowledge_links",
        project_id=project_id,
        status="pending",
        embedding_model=embedding_model.strip() if embedding_model else None,
        scope_json=scope,
        triggered_by_user_id=user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    send_tracked_task(
        db,
        run,
        "compute_knowledge_links",
        [run.id],
        {
            "trace_id": get_trace_id(),
            "min_confidence": min_confidence,
            "embedding_model": run.embedding_model or cfg.OLLAMA_EMBED_MODEL,
            "project_id": project_id,
            "source_ids": scope.get("source_ids"),
        },
        queue="global_link_runs",
    )
    return {
        "message": "Cross-Source Analyse gestartet",
        "run_id": run.id,
        "scope": run.scope_json,
        "deduplicated": False,
    }
