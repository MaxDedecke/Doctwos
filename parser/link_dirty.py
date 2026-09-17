"""Helpers for the persistent O-180 incremental link-builder queue."""

from models.database import LinkBuilderDirtyItem


def enqueue_dirty_item(
    db,
    *,
    project_id: int,
    entity_id: int | None = None,
    chunk_id: int | None = None,
    reason: str = "content_changed",
) -> LinkBuilderDirtyItem:
    """Add one coalesced pending item for an entity or a document chunk."""
    if entity_id is None and chunk_id is None:
        raise ValueError("A dirty link item needs an entity_id or chunk_id")

    query = db.query(LinkBuilderDirtyItem).filter(
        LinkBuilderDirtyItem.project_id == project_id,
        LinkBuilderDirtyItem.status == "pending",
        LinkBuilderDirtyItem.entity_id == entity_id,
        LinkBuilderDirtyItem.chunk_id == chunk_id,
    )
    item = query.first()
    if item is None:
        item = LinkBuilderDirtyItem(
            project_id=project_id,
            entity_id=entity_id,
            chunk_id=chunk_id,
            reason=reason,
            status="pending",
        )
        db.add(item)
    return item
