"""Umfang eines Entity-Link-Laufs: welche Code-Entitäten gegen welche Dokumentation geprüft werden.

Ein Lauf ohne Einschränkung folgt der Dirty-Queue (einmaliger Backfill, danach nur Geändertes). Ein
eingeschränkter Lauf (``scope_json["sets"]``, siehe ``doctus_models.link_sets``) prüft dagegen zwei feste
Mengen gegeneinander: Menge A (Code) gegen Menge B (Dokumentation). Er lässt die Dirty-Queue unberührt und
zählt nicht als Backfill, denn er hat nur einen Ausschnitt geprüft.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from sqlalchemy import or_

from core import config
from doctus_models.database import CodeEntity, DocumentChunk, LinkBuilderDirtyItem, LinkBuilderRun
from doctus_models.link_sets import DOCS, LinkSet, RunSets, code_scope, docs_scope

logger = logging.getLogger(__name__)


def embedding_model_filter(model: str):
    if model == config.EMBED_MODEL:
        return or_(DocumentChunk.embedding_model == model, DocumentChunk.embedding_model.is_(None))
    return DocumentChunk.embedding_model == model


def doc_chunk_conditions(
    project_id: int, embedding_model: str | None, docs_set: LinkSet | None = None
) -> list:
    """Filter der Dokumentationsseite eines Laufs; ``docs_set`` schränkt auf Menge B ein."""
    return [
        *docs_scope(project_id, docs_set or LinkSet.everything_of(DOCS)),
        embedding_model_filter(embedding_model or config.EMBED_MODEL),
    ]


def selected_entity_ids(db, project_id: int, code_set: LinkSet) -> set[int]:
    return {
        entity_id
        for (entity_id,) in db.query(CodeEntity.id).filter(*code_scope(project_id, code_set))
    }


# Obergrenze für den Arbeitsspeicher-Korpus des Keyword-Passes (Zeichen kleingeschriebenen Chunk-Texts).
# Darüber bleibt es beim bisherigen Lesen je Entity, damit ein sehr großer Bestand den Worker nicht sprengt.
KEYWORD_CORPUS_MAX_CHARS = int(os.getenv("LINK_KEYWORD_CORPUS_MAX_CHARS", str(400_000_000)))


class KeywordCorpus:
    """Kleingeschriebene Chunk-Texte eines Projekts, einmal je Lauf entschlüsselt.

    DocumentChunk.content ist at rest verschlüsselt; ein SQL-Filter auf den Inhalt ist nicht möglich. Statt für
    jede Entity alle Chunks erneut zu lesen und zu entschlüsseln (Kosten Entities x Chunks), liegt der Text
    einmal im Speicher. Die Treffer bleiben gleich: Teilstring-Suche, Reihenfolge nach Chunk-ID.
    """

    def __init__(
        self,
        db,
        project_id: int,
        embedding_model: str | None = None,
        docs_set: LinkSet | None = None,
    ):
        self.items: list[tuple[int, str]] | None = []
        total = 0
        # Ohne den Dokumentationsfilter kamen Quellcode-Abschnitte über die Stichwortsuche doch als Kandidaten
        # (Syncope, Lauf 158: 59 von 104 Vorschlägen zeigten auf .java/.groovy/.xml).
        rows = (
            db.query(DocumentChunk.id, DocumentChunk.content)
            .filter(*doc_chunk_conditions(project_id, embedding_model, docs_set))
            .order_by(DocumentChunk.id)
            .yield_per(500)
        )
        for chunk_id, content in rows:
            text = (content or "").lower()
            total += len(text)
            if total > KEYWORD_CORPUS_MAX_CHARS:
                self.items = None
                logger.warning(
                    "[LinkBuilder] Keyword-Korpus über %s Zeichen; lese je Entity",
                    KEYWORD_CORPUS_MAX_CHARS,
                )
                return
            self.items.append((chunk_id, text))


@dataclass
class RunSelection:
    """Welche Entities ein Lauf prüft und welche Queue-Einträge er dabei abarbeitet."""

    entities: list[CodeEntity]
    bootstrap: bool
    dirty_items: list = field(default_factory=list)
    dirty_entity_ids: set[int] = field(default_factory=set)
    dirty_chunk_ids: set[int] = field(default_factory=set)
    queue_ids: set[int] = field(default_factory=set)


def _had_full_run(db, project_id: int, run_id: int) -> bool:
    """Ein abgeschlossener Lauf ohne Einschränkung; ein eingeschränkter Lauf ersetzt den Backfill nicht."""
    rows = db.query(LinkBuilderRun.scope_json).filter(
        LinkBuilderRun.project_id == project_id,
        LinkBuilderRun.task_type == "entity_links",
        LinkBuilderRun.status == "completed",
        LinkBuilderRun.id != run_id,
    )
    return any(not (scope or {}).get("sets") for (scope,) in rows)


def select_run_entities(
    db,
    project_id: int,
    run_id: int,
    all_entities: list[CodeEntity],
    run_sets: RunSets,
    orphaned_entity_ids: set[int],
) -> RunSelection:
    if run_sets.targeted:
        # Zwei feste Mengen gegeneinander: jede Entity aus A gegen die gesamte Dokumentation aus B.
        wanted = selected_entity_ids(db, project_id, run_sets.a)
        entities = [entity for entity in all_entities if entity.id in wanted]
        logger.info(
            f"[LinkBuilder] Projekt {project_id}: eingeschränkter Lauf ({len(entities)} Entities)…"
        )
        return RunSelection(entities=entities, bootstrap=True)

    dirty_items = (
        db.query(LinkBuilderDirtyItem)
        .filter(
            LinkBuilderDirtyItem.project_id == project_id,
            LinkBuilderDirtyItem.status == "pending",
        )
        .all()
    )
    # Existing installations have no queue rows yet. The first run is a
    # one-time backfill; all later runs are driven exclusively by queue
    # entries created by ingestion.
    bootstrap = not dirty_items and not _had_full_run(db, project_id, run_id)
    dirty_entity_ids = {item.entity_id for item in dirty_items if item.entity_id is not None}
    # Vorschläge, deren Abschnitt ein Re-Index entfernt hat (chunk_id NULL), lassen sich weder anzeigen noch
    # über den Abschnitt ersetzen; ihre Entity wird gegen die aktuellen Abschnitte neu bewertet.
    dirty_entity_ids |= orphaned_entity_ids
    dirty_chunk_ids = {item.chunk_id for item in dirty_items if item.chunk_id is not None}
    queue_ids = {item.id for item in dirty_items}
    if bootstrap:
        logger.info(
            f"[LinkBuilder] Projekt {project_id}: einmaliger Backfill ({len(all_entities)} Entities)…"
        )
        return RunSelection(entities=list(all_entities), bootstrap=True)
    if dirty_chunk_ids:
        # A changed chunk may become relevant to any code entity, while an
        # entity-only change can be limited to that entity below.
        entities = list(all_entities)
        logger.info(
            f"[LinkBuilder] Projekt {project_id}: inkrementeller Lauf ({len(dirty_entity_ids)} Entities, {len(dirty_chunk_ids)} Chunks)…"
        )
    else:
        entities = [entity for entity in all_entities if entity.id in dirty_entity_ids]
        logger.info(
            f"[LinkBuilder] Projekt {project_id}: inkrementeller Lauf ({len(entities)} geänderte Entities)…"
        )
    return RunSelection(
        entities=entities,
        bootstrap=False,
        dirty_items=dirty_items,
        dirty_entity_ids=dirty_entity_ids,
        dirty_chunk_ids=dirty_chunk_ids,
        queue_ids=queue_ids,
    )
