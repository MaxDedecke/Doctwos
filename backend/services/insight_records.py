"""Detailed insight snapshots for explicit reads and writes."""

from doctus_models.database import Insight, KnowledgeSource
from doctus_models.insight_versions import capture_versions, version_state


def serialize_insight(insight: Insight, db=None) -> dict:
    current_versions = (
        capture_versions(db, insight.project_id, insight.evidence_json) if db is not None else []
    )
    state = version_state(db, insight, current_versions) if db is not None else "unknown"
    return {
        "evidence_count": len(insight.evidence_json or []),
        "needs_review": insight.status in {"draft", "outdated"}
        or (insight.status == "verified" and state not in {"current", "project"}),
        "owner_id": insight.owner_id,
        "reviewer_id": insight.reviewer_id,
        "priority": insight.priority,
        "due_at": insight.due_at.isoformat() if insight.due_at else None,
        "work_revision": insight.work_revision,
        "workflow_history": insight.workflow_history or [],
        "version_bindings": insight.version_bindings,
        "current_versions": current_versions,
        "version_state": state,
        "current_sources": [
            {
                "source_id": source.id,
                "last_synced_at": source.last_synced_at.isoformat()
                if source.last_synced_at
                else None,
                "commit": (source.sync_cursor or {}).get("last_commit"),
                "sync_status": source.sync_status,
            }
            for source in (
                db.query(KnowledgeSource)
                .filter(
                    KnowledgeSource.project_id == insight.project_id,
                    KnowledgeSource.id.in_(
                        [
                            e.get("source_id")
                            for e in insight.evidence_json
                            if e.get("source_id") is not None
                        ]
                    ),
                )
                .all()
                if db is not None
                else []
            )
        ],
        "revision": insight.revision,
        "review_history": insight.review_history or [],
        "id": insight.id,
        "project_id": insight.project_id,
        "title": insight.title,
        "content": insight.content,
        "origin_kind": insight.origin_kind,
        "evidence": insight.evidence_json,
        "status": insight.status,
        "created_by_id": insight.created_by_id,
        "created_at": insight.created_at.isoformat() if insight.created_at else None,
        "verified_by_id": insight.verified_by_id,
        "verified_at": insight.verified_at.isoformat() if insight.verified_at else None,
        "outdated_at": insight.outdated_at.isoformat() if insight.outdated_at else None,
        "outdated_source_ids": insight.outdated_source_ids or [],
    }
