"""Umfang eines Entity-Link-Laufs: welche Code-Entitäten gegen welche Dokumentation geprüft werden.

Ein Lauf ohne Einschränkung folgt der Dirty-Queue (einmaliger Backfill, danach nur Geändertes). Ein
eingeschränkter Lauf (``scope_json["filter"]``) prüft dagegen zwei feste Mengen gegeneinander: alle
Code-Entitäten der gewählten Typen gegen die Dokumentation der gewählten Wissensquellen. Er lässt die
Dirty-Queue unberührt und zählt nicht als Backfill, denn er hat nur einen Ausschnitt geprüft.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from sqlalchemy import or_, select

from core import config
from doctus_models.database import (
    CodeEntity,
    DocumentChunk,
    KnowledgeSource,
    LinkBuilderDirtyItem,
    LinkBuilderRun,
)

logger = logging.getLogger(__name__)

_DOC_LANGUAGES = ("asciidoc", "markdown", "text")


def embedding_model_filter(model: str):
    if model == config.EMBED_MODEL:
        return or_(DocumentChunk.embedding_model == model, DocumentChunk.embedding_model.is_(None))
    return DocumentChunk.embedding_model == model


def documentation_filter():
    """Nur Dokumentation ist Kandidat: Inhalte nicht-Git-Quellen sowie Doku-Dateien in Git-Quellen.

    Quellcode-Abschnitte einer Git-Quelle sind der Code selbst; Code-zu-Code-Beziehungen gehören in den
    Aufrufgraphen (gleiche Regel wie api/entity_links.py::search_doc_chunks).
    """
    non_git = DocumentChunk.source_id.in_(
        select(KnowledgeSource.id).where(KnowledgeSource.type != "Git")
    )
    doc_language = DocumentChunk.metadata_json["language"].as_string().in_(_DOC_LANGUAGES)
    return or_(non_git, doc_language)


def doc_chunk_conditions(
    project_id: int, embedding_model: str | None, doc_source_ids: frozenset[int] | None = None
) -> list:
    """Filter der Dokumentationsseite eines Laufs; ``doc_source_ids`` schränkt auf diese Quellen ein."""
    conditions = [
        DocumentChunk.project_id == project_id,
        DocumentChunk.source_id.isnot(None),
        embedding_model_filter(embedding_model or config.EMBED_MODEL),
        documentation_filter(),
    ]
    if doc_source_ids:
        conditions.append(DocumentChunk.source_id.in_(sorted(doc_source_ids)))
    return conditions


@dataclass(frozen=True)
class LinkRunScope:
    """Einschränkung eines Laufs; leer heißt: alle Code-Entitäten und alle Dokumentation."""

    entity_types: frozenset[str] = frozenset()
    doc_source_ids: frozenset[int] = frozenset()

    @property
    def targeted(self) -> bool:
        return bool(self.entity_types or self.doc_source_ids)

    @classmethod
    def from_scope(cls, scope: dict | None) -> "LinkRunScope":
        raw = (scope or {}).get("filter") or {}
        if not isinstance(raw, dict):
            return cls()
        types = frozenset(
            str(value).strip() for value in raw.get("entity_types") or [] if str(value).strip()
        )
        source_ids: set[int] = set()
        for value in raw.get("doc_source_ids") or []:
            try:
                source_ids.add(int(value))
            except (TypeError, ValueError):
                continue
        return cls(types, frozenset(source_ids))

    def includes(self, entity: CodeEntity) -> bool:
        return not self.entity_types or entity.type in self.entity_types


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
        doc_source_ids: frozenset[int] | None = None,
    ):
        self.items: list[tuple[int, str]] | None = []
        total = 0
        # Ohne den Dokumentationsfilter kamen Quellcode-Abschnitte über die Stichwortsuche doch als Kandidaten
        # (Syncope, Lauf 158: 59 von 104 Vorschlägen zeigten auf .java/.groovy/.xml).
        rows = (
            db.query(DocumentChunk.id, DocumentChunk.content)
            .filter(*doc_chunk_conditions(project_id, embedding_model, doc_source_ids))
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
    return any(not LinkRunScope.from_scope(scope).targeted for (scope,) in rows)


def select_run_entities(
    db,
    project_id: int,
    run_id: int,
    all_entities: list[CodeEntity],
    run_scope: LinkRunScope,
    orphaned_entity_ids: set[int],
) -> RunSelection:
    if run_scope.targeted:
        # Zwei feste Mengen gegeneinander: jede gewählte Entity gegen die gesamte gewählte Dokumentation.
        entities = [entity for entity in all_entities if run_scope.includes(entity)]
        logger.info(
            f"[LinkBuilder] Projekt {project_id}: eingeschränkter Lauf ({len(entities)} Entities, "
            f"Typen {sorted(run_scope.entity_types) or 'alle'}, Quellen {sorted(run_scope.doc_source_ids) or 'alle'})…"
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
