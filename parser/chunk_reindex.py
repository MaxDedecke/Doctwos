"""
Shared delete-and-recreate reindex, used by every ingestion path that
replaces a document's or a git file's chunks (local upload, every
BaseConnector subclass: Confluence, Jira, Notion, Dalux, Autodesk ACC/BIM
360, WebDAV -- and tasks/repository.py's git delta sync).

Re-indexing gives every new chunk a fresh id. EntityDocLink.chunk_id has
ON DELETE SET NULL, which otherwise silently detaches an "approved" link
from its passage while leaving the status untouched -- a document could
change underneath a link a reviewer already signed off on, and nothing
would notice. This module snapshots affected links by content fingerprint
before the delete and rewires them afterwards if the passage survived
unchanged; anything that can't be matched 1:1 falls back to "pending"
instead of staying silently "approved" against a dead/changed chunk_id.
"""

import hashlib
from typing import Awaitable, Callable, Optional

from sqlalchemy import ColumnElement

from models.database import DocumentChunk, EntityDocLink
from link_dirty import enqueue_dirty_item

STALE_NOTE = "[Inhalt bei Re-Index geändert – erneute Prüfung nötig] "


def content_fingerprint(content: str) -> str:
    """Whitespace-normalized content hash, used to recognize an unchanged
    passage across re-index even if PDF extraction jitter or pagination
    shifts start_line/end_line."""
    return hashlib.sha256(" ".join(content.split()).encode("utf-8")).hexdigest()


async def reindex_chunks_preserving_links(
    db,
    *,
    file_path: str,
    chunks: list[dict],
    build_chunk: Callable[[dict, list[float]], DocumentChunk],
    embed_content: Optional[Callable[[str], Awaitable[list[float]]]] = None,
    on_embed_error: Optional[Callable[[dict, Exception], None]] = None,
    source_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> int:
    """
    Replaces all DocumentChunk rows for (file_path, scope) with freshly
    embedded `chunks`, preserving EntityDocLink status/chunk_id across the
    swap wherever content didn't actually change.

    Scope is exactly one of `source_id` (KnowledgeSource-backed documents:
    local upload, connectors) or `project_id` (git repositories -- those
    chunks never carry a source_id). The two are mutually exclusive because
    a DocumentChunk row only ever populates one of them.

    build_chunk(chunk, embedding) must return an unsaved DocumentChunk for
    the given parsed chunk dict. A chunk dict that already carries a
    precomputed "embedding" (git delta sync embeds concurrently upstream
    across many files, unlike the single-document connector paths) is used
    as-is; otherwise embed_content(content) is awaited to produce it.

    Returns the number of chunks successfully embedded and stored.
    """
    if (source_id is None) == (project_id is None):
        raise ValueError(
            "reindex_chunks_preserving_links requires exactly one of source_id or project_id"
        )
    scope: ColumnElement = (
        DocumentChunk.source_id == source_id
        if source_id is not None
        else DocumentChunk.project_id == project_id
    )

    old_chunks = (
        db.query(DocumentChunk)
        .filter(
            scope,
            DocumentChunk.file_path == file_path,
        )
        .all()
    )
    old_chunk_ids = [c.id for c in old_chunks]

    links_by_old_fingerprint: dict[str, list[EntityDocLink]] = {}
    old_fingerprint_by_chunk_id: dict[int, str] = {}
    if old_chunks:
        old_fingerprint_by_chunk_id = {
            c.id: c.content_hash or content_fingerprint(c.content) for c in old_chunks
        }
        affected_links = (
            db.query(EntityDocLink)
            .filter(EntityDocLink.chunk_id.in_(old_fingerprint_by_chunk_id.keys()))
            .all()
        )
        for link in affected_links:
            fp = old_fingerprint_by_chunk_id.get(link.chunk_id)
            if fp:
                links_by_old_fingerprint.setdefault(fp, []).append(link)

    # New chunks are created (and, below, links rewired/downgraded) BEFORE the
    # old rows are deleted -- deliberately the reverse of the obvious
    # delete-then-recreate order. Postgres CHECK constraints (unlike FK/unique
    # constraints) can't be made DEFERRABLE, so
    # ck_entity_doc_links_approved_requires_chunk_or_manual is evaluated the
    # instant ON DELETE SET NULL touches a row -- if that row were still
    # "approved" at delete time, the delete itself would raise. Rewiring a
    # link onto its new chunk_id, or downgrading it off "approved", before the
    # delete runs means the FK action either skips the row (already pointing
    # elsewhere) or trivially satisfies the constraint (no longer approved).
    embedded_count = 0
    old_chunks_by_fingerprint: dict[str, list[DocumentChunk]] = {}
    for old_chunk in old_chunks:
        old_chunks_by_fingerprint.setdefault(
            old_fingerprint_by_chunk_id[old_chunk.id], []
        ).append(old_chunk)
    old_count_by_fingerprint = {
        fingerprint: len(matches)
        for fingerprint, matches in old_chunks_by_fingerprint.items()
    }
    # Values are lists, not a single id: two chunks can share a fingerprint
    # (repeated boilerplate clauses, headers/footers, standard legal
    # citations). A dict last-wins here would silently rewire an approved
    # link onto the wrong passage. Only rewire on an unambiguous 1:1 match.
    new_chunk_ids_by_fingerprint: dict[str, list[int]] = {}
    for chunk in chunks:
        if "embedding" in chunk:
            embedding = chunk["embedding"]
        else:
            try:
                embedding = await embed_content(chunk["content"])
                if not embedding:
                    raise ValueError(
                        "Embedding-Modell lieferte leeren Vektor (vermutlich whitespace-/leerer Chunk-Inhalt)"
                    )
            except Exception as e:
                if on_embed_error:
                    on_embed_error(chunk, e)
                continue

        db_chunk = build_chunk(chunk, embedding)
        fingerprint = content_fingerprint(chunk["content"])
        db_chunk.content_hash = fingerprint

        # A chunk gets a new database id on every re-index. Reuse the link
        # revision only when this occurrence has the same content and model as
        # an old occurrence; otherwise it is a new dirty candidate.
        matching_old = old_chunks_by_fingerprint.get(fingerprint, [])
        old_match = matching_old.pop(0) if matching_old else None
        old_model = old_match.embedding_model if old_match is not None else None
        new_model = db_chunk.embedding_model
        model_changed = old_match is not None and old_model != new_model
        if old_match is not None and not model_changed:
            db_chunk.link_revision = old_match.link_revision or 0
        else:
            db_chunk.link_revision = 1

        db.add(db_chunk)
        db.flush()  # assign id for link rewiring and the dirty queue
        if (
            project_id is not None
            and db_chunk.source_id is not None
            and (old_match is None or model_changed)
        ):
            enqueue_dirty_item(
                db,
                project_id=project_id,
                chunk_id=db_chunk.id,
                reason="embedding_model_changed" if model_changed else "content_changed",
            )
        if links_by_old_fingerprint:
            new_chunk_ids_by_fingerprint.setdefault(
                fingerprint, []
            ).append(db_chunk.id)
        embedded_count += 1

    for fingerprint, links in links_by_old_fingerprint.items():
        candidates = new_chunk_ids_by_fingerprint.get(fingerprint, [])
        new_chunk_id = (
            candidates[0]
            if len(candidates) == 1 and old_count_by_fingerprint.get(fingerprint) == 1
            else None
        )
        for link in links:
            if new_chunk_id is not None:
                link.chunk_id = new_chunk_id
            elif link.status == "approved":
                link.status = "pending"
                link.score = None
                link.reviewed_at = None
                if not (link.context or "").startswith(STALE_NOTE):
                    link.context = STALE_NOTE + (link.context or "")
            elif link.status == "pending" and link.created_by == "auto":
                # Pending recommendations are derived work products. Once the
                # old passage has no unambiguous successor, remove only this
                # stale automatic suggestion; manual links remain untouched.
                db.delete(link)
    if links_by_old_fingerprint:
        db.flush()

    # Target the old rows by id, not by (scope, file_path): the new rows just
    # inserted above share that same (scope, file_path) and must survive.
    db.query(DocumentChunk).filter(DocumentChunk.id.in_(old_chunk_ids)).delete(
        synchronize_session=False
    )

    return embedded_count
