"""Wechsel des Embedding-Modells eines Projekts ohne Ausfall der Suche (Blue-Green über einen Schattenvektor).

Ablauf (``EmbeddingMigration.status``):

    embedding  Jeder Abschnitt des Projekts bekommt in ``embedding_next`` den Vektor des Zielmodells. Die Suche nutzt
               weiter den alten Vektor. In Stapeln, je Stapel ein Commit; ein abgebrochener Lauf setzt dort fort, wo
               noch kein Schattenvektor des Zielmodells steht.
    ready      Alle Abschnitte haben einen Schattenvektor. Jetzt lässt sich die Suchqualität prüfen
               (``scripts/eval_search.py``) und umschalten.
    switched   Umschalten: Syncs der Projektquellen gesperrt, Abschnitte, die seit dem Lauf neu entstanden sind,
               nachgezogen, dann in einer Transaktion alter und neuer Vektor getauscht und die Quellen auf das neue
               Modell gestellt. Der alte Vektor liegt danach im Schatten; die Rücknahme tauscht zurück.
    cleaned    Schattenvektoren entfernt; keine Rücknahme mehr.

Nebenzustände: ``failed`` (Lauf fortsetzbar), ``cancelled``, ``rolled_back``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, or_, text
from sqlalchemy.orm import load_only

from core.sync_lock import SyncLock
from db import SessionLocal
from codena_models.database import DocumentChunk, EmbeddingMigration, KnowledgeSource
from codena_models.vector_index import create_index_sql
from ollama_client import get_embeddings_batch

logger = logging.getLogger(__name__)

BATCH = 64
OPEN_STATES = {"embedding", "ready", "switched"}


class MigrationBlocked(RuntimeError):
    """Umschalten oder Zurücknehmen ist gerade nicht möglich (etwa weil ein Sync läuft)."""


def _project_scope(db, project_id: int):
    source_ids = [
        sid
        for (sid,) in db.query(KnowledgeSource.id).filter(KnowledgeSource.project_id == project_id)
    ]
    scope = DocumentChunk.project_id == project_id
    if source_ids:
        scope = or_(
            scope,
            and_(DocumentChunk.project_id.is_(None), DocumentChunk.source_id.in_(source_ids)),
        )
    return scope


def _pending(db, project_id: int, model: str):
    """Abschnitte ohne Vektor des Modells, weder im Haupt- noch im Schattenvektor."""
    return db.query(DocumentChunk).filter(
        _project_scope(db, project_id),
        DocumentChunk.embedding_model.is_distinct_from(model),
        DocumentChunk.embedding_next_model.is_distinct_from(model),
    )


def _load(db, migration_id: int) -> EmbeddingMigration:
    migration = db.query(EmbeddingMigration).filter(EmbeddingMigration.id == migration_id).first()
    if migration is None:
        raise LookupError(f"Modellwechsel {migration_id} nicht gefunden")
    return migration


async def _fill(db, migration: EmbeddingMigration, model: str) -> int:
    """Schattenvektoren des Modells für alle noch fehlenden Abschnitte; liefert die Zahl der neuen Vektoren."""
    written = 0
    last_id = 0
    while True:
        db.refresh(migration)
        if migration.status == "cancelled":
            return written
        rows = (
            _pending(db, migration.project_id, model)
            .filter(DocumentChunk.id > last_id)
            .options(load_only(DocumentChunk.id, DocumentChunk.content))
            .order_by(DocumentChunk.id)
            .limit(BATCH)
            .all()
        )
        if not rows:
            return written
        last_id = rows[-1].id
        vectors = await get_embeddings_batch([row.content or "" for row in rows], model=model)
        if migration.target_dimension is None and vectors and model == migration.target_model:
            migration.target_dimension = len(vectors[0])
        db.bulk_update_mappings(
            DocumentChunk,
            [
                {"id": row.id, "embedding_next": vector, "embedding_next_model": model}
                for row, vector in zip(rows, vectors)
            ],
        )
        written += len(rows)
        if model == migration.target_model:
            migration.done = (migration.done or 0) + len(rows)
        db.commit()


def _swap(db, project_id: int, from_model: str, to_model: str) -> int:
    """Tauscht Haupt- und Schattenvektor aller Abschnitte, deren Schatten das Zielmodell trägt (eine Transaktion).

    In PostgreSQL sehen alle Ausdrücke einer UPDATE-Zeile die alten Werte; ``embedding = embedding_next,
    embedding_next = embedding`` tauscht also wirklich.
    """
    scope_sql = (
        "(c.project_id = :pid OR (c.project_id IS NULL AND c.source_id IN "
        "(SELECT id FROM knowledge_sources WHERE project_id = :pid)))"
    )
    result = db.execute(
        text(
            "UPDATE document_chunks c SET embedding = c.embedding_next, embedding_next = c.embedding, "
            "embedding_model = c.embedding_next_model, embedding_next_model = c.embedding_model, "
            "embedding_dimension = vector_dims(c.embedding_next) "
            f"WHERE {scope_sql} AND c.embedding_next_model = :to_model AND c.embedding_next IS NOT NULL"
        ),
        {"pid": project_id, "to_model": to_model},
    )
    db.query(KnowledgeSource).filter(KnowledgeSource.project_id == project_id).update(
        {KnowledgeSource.embedding_model: to_model}, synchronize_session=False
    )
    return result.rowcount or 0


def _locks(db, project_id: int) -> list[SyncLock]:
    """Sperrt die Syncs aller Projektquellen, damit während des Tauschs keine Abschnitte im alten Raum entstehen."""
    held: list[SyncLock] = []
    for (sid,) in db.query(KnowledgeSource.id).filter(KnowledgeSource.project_id == project_id):
        lock = SyncLock(sid)
        if not lock.acquire():
            for other in held:
                other.release()
            raise MigrationBlocked(
                "Eine Quelle des Projekts synchronisiert gerade; nach ihrem Ende erneut versuchen."
            )
        held.append(lock)
    return held


def _ensure_index(db, dimension: int | None) -> None:
    sql = create_index_sql(dimension or 0)
    if sql is None:
        logger.warning(
            "Dimension %s ist nicht HNSW-indizierbar; die Suche liest alle Abschnitte.", dimension
        )
        return
    db.execute(text(sql))
    db.commit()


async def run(migration_id: int) -> None:
    db = SessionLocal()
    try:
        migration = _load(db, migration_id)
        if migration.status not in ("embedding", "failed"):
            return
        migration.status = "embedding"
        migration.error = None
        db.commit()
        try:
            await _fill(db, migration, migration.target_model)
        except Exception as exc:  # noqa: BLE001 - der Lauf ist fortsetzbar, der Fehler gehört in die Anzeige
            db.rollback()
            migration = _load(db, migration_id)
            migration.status = "failed"
            migration.error = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
            logger.exception("Modellwechsel %s: Einbetten fehlgeschlagen", migration_id)
            return
        db.refresh(migration)
        if migration.status == "embedding":
            migration.status = "ready"
            db.commit()
    finally:
        db.close()


async def switch(migration_id: int) -> None:
    await _flip(migration_id, expected="ready", forward=True)


async def rollback(migration_id: int) -> None:
    await _flip(migration_id, expected="switched", forward=False)


async def _flip(migration_id: int, *, expected: str, forward: bool) -> None:
    db = SessionLocal()
    locks: list[SyncLock] = []
    try:
        migration = _load(db, migration_id)
        if migration.status != expected:
            return
        to_model = migration.target_model if forward else migration.previous_model
        from_model = migration.previous_model if forward else migration.target_model
        if not to_model:
            raise MigrationBlocked("Ausgangsmodell unbekannt; Rücknahme nicht möglich.")
        try:
            locks = _locks(db, migration.project_id)
            # Seit dem Lauf neu entstandene Abschnitte (bzw. beim Zurücknehmen: seit dem Umschalten) nachziehen.
            await _fill(db, migration, to_model)
            dimension = migration.target_dimension if forward else None
            if dimension is None:
                probe = (
                    db.query(DocumentChunk)
                    .filter(
                        _project_scope(db, migration.project_id),
                        DocumentChunk.embedding_next_model == to_model,
                    )
                    .options(load_only(DocumentChunk.id, DocumentChunk.embedding_next))
                    .first()
                )
                dimension = (
                    len(probe.embedding_next)
                    if probe is not None and probe.embedding_next is not None
                    else None
                )
            _ensure_index(db, dimension)
            swapped = _swap(db, migration.project_id, from_model, to_model)
            migration.status = "switched" if forward else "rolled_back"
            migration.switched_at = datetime.now(timezone.utc) if forward else migration.switched_at
            migration.error = None
            db.commit()
            logger.info(
                "Modellwechsel %s: %s Abschnitte auf %s umgestellt", migration_id, swapped, to_model
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            migration = _load(db, migration_id)
            migration.error = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
            logger.warning("Modellwechsel %s: Umschalten nicht möglich: %s", migration_id, exc)
    finally:
        for lock in locks:
            lock.release()
        db.close()


def cleanup(migration_id: int) -> None:
    db = SessionLocal()
    try:
        migration = _load(db, migration_id)
        if migration.status not in ("switched", "rolled_back", "cancelled", "failed"):
            return
        db.query(DocumentChunk).filter(
            _project_scope(db, migration.project_id), DocumentChunk.embedding_next.isnot(None)
        ).update(
            {DocumentChunk.embedding_next: None, DocumentChunk.embedding_next_model: None},
            synchronize_session=False,
        )
        migration.status = "cleaned"
        db.commit()
    finally:
        db.close()
