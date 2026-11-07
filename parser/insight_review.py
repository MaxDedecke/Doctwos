"""Escalate evidence-backed findings when a referenced source has changed."""

from datetime import datetime, timezone
from typing import Any

from doctus_models.database import Insight, KnowledgeSource
from doctus_models.insight_evidence import file_fingerprint
from doctus_models.insight_versions import capture_versions, versions_match


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
    for insight in (
        db.query(Insight)
        .filter(
            Insight.project_id == source.project_id,
            Insight.status == "verified",
        )
        .with_for_update()
        .all()
    ):
        if not _references_source(insight.evidence_json, source.id) and not _references_source(
            insight.version_bindings or [], source.id
        ):
            continue
        references = [e for e in insight.evidence_json if e.get("source_id") == source.id]
        versions_changed = insight.version_bindings is not None and not versions_match(
            insight.version_bindings,
            capture_versions(db, insight.project_id, insight.evidence_json),
        )
        if (
            not versions_changed
            and references
            and all(
                e.get("file_fingerprint")
                and e.get("file")
                and e["file_fingerprint"]
                == file_fingerprint(db, insight.project_id, source.id, e["file"])
                for e in references
            )
        ):
            continue
        prior_ids = set(insight.outdated_source_ids or [])
        prior_ids.add(source.id)
        insight.revision = (insight.revision or 1) + 1
        insight.status = "outdated"
        insight.outdated_at = datetime.now(timezone.utc)
        insight.outdated_source_ids = sorted(prior_ids)
        affected += 1
    return affected
