"""Small, shared provenance payloads for claims shown across user workflows."""

from __future__ import annotations

from typing import Any


def source_revision(source: Any, metadata: dict | None = None) -> tuple[str | None, str | None]:
    """Return the best revision identifier we have without inventing one."""
    metadata = metadata if isinstance(metadata, dict) else {}
    spaces = getattr(source, "spaces", None)
    spaces = spaces if isinstance(spaces, dict) else {}
    cursor = getattr(source, "sync_cursor", None)
    cursor = cursor if isinstance(cursor, dict) else {}

    commit = metadata.get("source_revision") or cursor.get("last_commit") or spaces.get("last_commit_hash")
    if commit:
        return str(commit), "commit"
    content_hash = metadata.get("content_hash")
    if content_hash:
        return str(content_hash), "content_hash"
    return None, None


def build_provenance(
    source: Any | None,
    *,
    kind: str,
    verification_status: str,
    locator: dict | None = None,
    metadata: dict | None = None,
    detail: str | None = None,
    association_status: str | None = None,
    association_reviewed_at: str | None = None,
    certainty: str | None = None,
    origin: str | None = None,
    analysis_status: str | None = None,
    analysis_reasons: list[str] | None = None,
) -> dict:
    """Build a JSON-safe provenance record; association review stays distinct
    from review of the claim itself.
    """
    revision, revision_kind = source_revision(source, metadata)
    synced_at = getattr(source, "last_synced_at", None) if source else None
    spaces = getattr(source, "spaces", None) if source else None
    spaces = spaces if isinstance(spaces, dict) else {}
    return {
        "kind": kind,
        "verification_status": verification_status,
        "verification_note": detail,
        "source_id": getattr(source, "id", None) if source else None,
        "source_name": getattr(source, "name", None) if source else None,
        "source_type": getattr(source, "type", None) if source else None,
        "source_revision": revision,
        "revision_kind": revision_kind,
        "branch": (getattr(source, "branch", None) or spaces.get("branch")) if source else None,
        "last_synced_at": synced_at.isoformat() if synced_at else None,
        "sync_status": getattr(source, "sync_status", None) if source else None,
        "association_status": association_status,
        "association_reviewed_at": association_reviewed_at,
        "certainty": certainty,
        "origin": origin,
        "analysis_status": analysis_status,
        "analysis_reasons": analysis_reasons or [],
        "locator": locator or {},
    }
