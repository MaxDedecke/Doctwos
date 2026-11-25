"""Transactional inbox events shared by API and source-sync workers."""

import hashlib
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from .database import InsightNotification


def notify_insight(db, insight, kind, *, actor_id=None, recipients=None):
    targets = set(
        recipients
        if recipients is not None
        else (
            insight.owner_id,
            insight.reviewer_id or insight.verified_by_id,
        )
    )
    cycle = f"{insight.revision}:{insight.work_revision or 1}"
    for user_id in targets - {None, actor_id}:
        db.execute(
            insert(InsightNotification)
            .values(
                insight_id=insight.id,
                project_id=insight.project_id,
                user_id=user_id,
                kind=kind,
                cycle_key=cycle,
            )
            .on_conflict_do_nothing(constraint="uq_insight_notification_cycle")
        )


def content_hash(insight):
    return hashlib.sha256((insight.title + "\n" + insight.content).encode()).hexdigest()


def embedding_profile_key(settings):
    settings = dict(settings)
    settings["provider"] = str(settings.get("provider") or "").lower()
    settings["base_url"] = str(settings.get("base_url") or "").rstrip("/")
    settings["path"] = settings.get("path") or (
        "/api/embed" if settings["provider"] == "ollama" else "/embeddings"
    )
    fields = ("provider", "base_url", "model", "path", "dimension", "context")
    return hashlib.sha256("|".join(str(settings.get(k) or "") for k in fields).encode()).hexdigest()


def embedding_text(insight, budget=4000):
    return (
        (insight.title + "\n" + insight.content)
        .encode()[: min(budget, 4000)]
        .decode("utf-8", errors="ignore")
    )


def touched(insight):
    insight.updated_at = datetime.now(timezone.utc)
