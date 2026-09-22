"""Escalate evidence-backed findings when a referenced source has changed."""

from datetime import datetime, timezone
from typing import Any

from models.database import Insight, KnowledgeSource


def _references_source(value: Any, source_id: int) -> bool:
    if isinstance(value, dict):
        if value.get("source_id") == source_id:
            return True
        return any(_references_source(item, source_id) for item in value.values())
    if isinstance(value, list):
        return any(_references_source(item, source_id) for item in value)
    return False


def mark_source_insights_outdated(db, source: KnowledgeSource) -> int:
    """Move only previously approved, actually source-backed insights to review.

    Drafts are already awaiting review.  The original verifier is retained so
    the UI can distinguish a source-change review from a new, unreviewed claim.
    """
    if source.project_id is None:
        return 0
    affected = 0
    for insight in db.query(Insight).filter(
        Insight.project_id == source.project_id,
        Insight.status == "verified",
    ).all():
        if not _references_source(insight.evidence_json, source.id):
            continue
        prior_ids = set(insight.outdated_source_ids or [])
        prior_ids.add(source.id)
        insight.status = "outdated"
        insight.outdated_at = datetime.now(timezone.utc)
        insight.outdated_source_ids = sorted(prior_ids)
        affected += 1
    return affected
