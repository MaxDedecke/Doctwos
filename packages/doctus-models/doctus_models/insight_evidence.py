"""Stable file fingerprints shared by insight creation and source-change review."""

import hashlib
from .database import CodeEntity, DocumentChunk


def file_fingerprint(db, project_id, source_id, path):
    chunks = (
        db.query(DocumentChunk.content_hash)
        .filter(
            DocumentChunk.project_id == project_id,
            DocumentChunk.source_id == source_id,
            DocumentChunk.file_path == path,
        )
        .all()
    )
    if not chunks or any(not value for (value,) in chunks):
        return None
    return hashlib.sha256("\n".join(sorted(value for (value,) in chunks)).encode()).hexdigest()


def snapshot_evidence(db, project_id, evidence):
    result = []
    for item in evidence:
        snapshot = dict(item)
        if snapshot.get("entity_id") is not None:
            entity = (
                db.query(CodeEntity)
                .filter_by(id=snapshot["entity_id"], project_id=project_id)
                .first()
            )
            if entity:
                snapshot.update(source_id=entity.source_id, file=entity.file_path)
        if snapshot.get("file") and snapshot.get("source_id") is not None:
            fingerprint = file_fingerprint(db, project_id, snapshot["source_id"], snapshot["file"])
            snapshot.pop("file_fingerprint", None)
            if fingerprint:
                snapshot["file_fingerprint"] = fingerprint
        result.append(snapshot)
    return result
