"""
parser/tasks/link_builder.py
=============================
2-Pass-Scan zur Erkennung von Verknüpfungen zwischen Code-Entities und Wissens-Chunks.

Pass 1 — Semantic:   Cosine-Ähnlichkeit via Embeddings (config.EMBED_MODEL)
Pass 2 — Keyword:    Token-Suche: Entity-Name und Dateipfad werden aufgesplittet
                     (Bindestriche, Underscores) und in Python gegen den entschlüsselten
                     Chunk-Content gesucht (DocumentChunk.content ist at rest verschlüsselt,
                     daher kein SQL ILIKE mehr möglich)

Die beiden Ergebnisse werden gemergt (höchster Score pro Seite gewinnt). Jede
EntityDocLink bekommt einen link_type ("semantic" | "keyword"), der im
Link-Manager-Frontend angezeigt wird. An das LLM (Pass 3) geht dabei jeder
gemergte Kandidat mit heuristischem Score über MERGE_SCORE_THRESHOLD (90%) —
kein Top-N-Deckel mehr, damit ein Entity mit vielen sehr ähnlichen Treffern
nicht willkürlich welche davon verliert (Nutzerentscheidung 10.08.2026, löst
den bisherigen TOP_PAGES=5-Deckel ab).

Pass 3 — LLM-Review:  Ein LLM-Call pro Entity bewertet die gemergten Kandidaten,
                       verwirft schwache/falsche Treffer und schreibt eine echte
                       Begründung (EntityDocLink.context). Ersetzt den Heuristik-
                       Score durch die LLM-Konfidenz. Kein Auto-Approve — die
                       Links landen weiterhin als "pending" im Review-Workflow.

Nur "approved" Links werden vom Agent und Monaco-Tooltips verwendet.
Bestehende approved/rejected Links werden nie überschrieben.
"""

import logging
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from db import SessionLocal, REDIS_URL
from models.database import (
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    LinkBuilderDirtyItem,
    LinkBuilderRun,
)
from ollama_client import get_embedding, get_chat_json, ensure_model_pulled
from core import config
from chunk_reindex import content_fingerprint
import redis
from celery import current_app
from sqlalchemy import or_

logger = logging.getLogger(__name__)

redis_client = redis.from_url(REDIS_URL)

MIN_SCORE_SEMANTIC = 0.45
MIN_SCORE_KEYWORD = 0.30

# Lease-Dauer des Redis-Locks. Kein fixes 1h-TTL mehr — stattdessen eine kurze
# Lease, die pro verarbeiteter Entity erneuert wird (siehe Heartbeat weiter
# unten). Ein legitim lang laufender Task (viele Entities) bleibt so beliebig
# lange gesperrt, solange er sichtbar Fortschritt macht; stirbt der Worker-
# Prozess hart (OOM-Kill etc.) und erneuert nicht mehr, läuft die Sperre nach
# LOCK_LEASE_SECONDS ab statt eine volle Stunde zu blockieren.
LOCK_LEASE_SECONDS = 120
TOP_CHUNKS_SEMANTIC = 20
TOP_CHUNKS_KEYWORD = 50
# Ersetzt den früheren TOP_PAGES=5-Deckel: statt der besten 5 Kandidaten geht
# jeder gemergte Kandidat mit heuristischem Score über dieser Schwelle ans LLM
# (Pass 1/2-Scores sind bereits auf 0..1 normiert, siehe MIN_SCORE_SEMANTIC/
# MIN_SCORE_KEYWORD oben). Kandidatenzahl bleibt trotzdem natürlich begrenzt
# durch TOP_CHUNKS_SEMANTIC/TOP_CHUNKS_KEYWORD.
MERGE_SCORE_THRESHOLD = 0.90
LLM_MIN_CONFIDENCE = 35


def _embedding_model_filter(model: str):
    if model == config.EMBED_MODEL:
        return or_(DocumentChunk.embedding_model == model, DocumentChunk.embedding_model.is_(None))
    return DocumentChunk.embedding_model == model


def _keywords_from_entity(entity: CodeEntity) -> list[str]:
    tokens = re.split(r"[-_]", entity.name)
    tokens += re.split(r"[-_]", os.path.splitext(os.path.basename(entity.file_path))[0])
    seen, result = set(), []
    for t in tokens:
        t = t.lower()
        if len(t) >= 3 and t not in seen:
            seen.add(t)
            result.append(t)
    return result


async def _pass_semantic(
    entity: CodeEntity,
    project_id: int,
    db,
    embedding_model: str | None = None,
    candidate_chunk_ids: set[int] | None = None,
) -> dict[str, tuple]:
    """Pass 1: cosine similarity between entity context and doc chunk embeddings."""
    selected_model = embedding_model or config.EMBED_MODEL
    model_filter = _embedding_model_filter(selected_model)
    context = f"{entity.type}: {entity.name} in {entity.file_path}"
    try:
        embedding = await get_embedding(context, model=selected_model)
    except Exception as e:
        logger.error(f"[LinkBuilder] Embedding failed for {entity.name}: {e}")
        return {}

    dist_expr = DocumentChunk.embedding.cosine_distance(embedding)
    query = db.query(DocumentChunk, dist_expr.label("dist")).filter(
        DocumentChunk.project_id == project_id,
        DocumentChunk.source_id.isnot(None),
        model_filter,
        DocumentChunk.embedding_dimension == len(embedding),
    )
    if candidate_chunk_ids is not None:
        query = query.filter(DocumentChunk.id.in_(candidate_chunk_ids))
    rows = query.order_by(dist_expr).limit(TOP_CHUNKS_SEMANTIC).all()

    result: dict[str, tuple] = {}
    for chunk, dist in rows:
        score = max(0.0, 1.0 - float(dist))
        if score < MIN_SCORE_SEMANTIC:
            continue
        meta = chunk.metadata_json or {}
        title = meta.get("title") or chunk.file_path
        if title not in result or score > result[title][1]:
            result[title] = (chunk, score)
    return result


def _pass_keyword(
    entity: CodeEntity,
    project_id: int,
    db,
    embedding_model: str | None = None,
    candidate_chunk_ids: set[int] | None = None,
) -> dict[str, tuple]:
    """Pass 2: token-based search — splits entity name/path and matches against chunk content.

    DocumentChunk.content is Fernet-encrypted at rest (EncryptedString), so this can no longer
    filter with SQL ILIKE -- candidates are fetched by the existing project_id/source_id scope
    and matched against the keywords in Python after decryption instead.
    """
    selected_model = embedding_model or config.EMBED_MODEL
    model_filter = _embedding_model_filter(selected_model)
    keywords = _keywords_from_entity(entity)
    if not keywords:
        return {}

    query = db.query(DocumentChunk).filter(
        DocumentChunk.project_id == project_id,
        DocumentChunk.source_id.isnot(None),
        model_filter,
    )
    if candidate_chunk_ids is not None:
        query = query.filter(DocumentChunk.id.in_(candidate_chunk_ids))
    candidates = query.all()

    result: dict[str, tuple] = {}
    matched_chunks = 0
    for chunk in candidates:
        content_lower = (chunk.content or "").lower()
        matched = sum(1 for kw in keywords if kw in content_lower)
        if matched == 0:
            continue
        matched_chunks += 1
        if matched_chunks > TOP_CHUNKS_KEYWORD:
            break
        score = matched / len(keywords)
        if score < MIN_SCORE_KEYWORD:
            continue
        meta = chunk.metadata_json or {}
        title = meta.get("title") or chunk.file_path
        if title not in result or score > result[title][1]:
            result[title] = (chunk, score)
    return result


def _merge_passes(*passes) -> list[tuple[DocumentChunk, float, str]]:
    merged: dict[str, tuple[DocumentChunk, float, str]] = {}
    for data, name in passes:
        for title, (chunk, score) in data.items():
            if title not in merged or score > merged[title][1]:
                merged[title] = (chunk, score, name)

    sorted_pages = sorted(merged.values(), key=lambda x: x[1], reverse=True)
    return [page for page in sorted_pages if page[1] > MERGE_SCORE_THRESHOLD]


async def _llm_review(
    entity: CodeEntity,
    top_pages: list[tuple[DocumentChunk, float, str]],
    min_confidence: int = LLM_MIN_CONFIDENCE,
) -> list[tuple[DocumentChunk, float, str, str]]:
    if not top_pages:
        return []

    prompt = (
        f"Du bist ein Programmier- und Code-Dokumentations-Experte.\n"
        f"Wir wollen entscheiden, ob die folgenden Dokumentationsabschnitte relevant sind für diese Code-Entity:\n"
        f"Entity: [{entity.type}] {entity.name} in Datei '{entity.file_path}'\n\n"
        f"Kandidaten-Dokumente:\n"
    )
    for idx, (chunk, score, link_type) in enumerate(top_pages):
        meta = chunk.metadata_json or {}
        title = meta.get("title") or chunk.file_path
        prompt += f"Index {idx}: [{meta.get('source_type')}] '{title}'\nInhalt: {chunk.content[:250]}...\n\n"

    prompt += (
        "Gib deine Bewertung als valides JSON-Array von Objekten zurück (eines pro Kandidat, in derselben Reihenfolge):\n"
        "[\n"
        "  {\n"
        '    "index": 0,\n'
        '    "confidence": 85, // Ganzzahl 0-100, wie sicher bist du bezüglich der Relevanz\n'
        '    "reason": "Erkläre kurz in 1-2 Sätzen, warum diese Doku für die Entity wichtig ist."\n'
        "  }\n"
        "]\n"
    )

    try:
        response = await get_chat_json(prompt, config.LLM_MODEL)
        # Ollamas format="json" erzwingt beim Modell ein JSON-*Objekt*, nie ein
        # rohes Top-Level-Array (beobachtet z.B. {"valid_json_array": [...]}
        # mit beliebigem, nicht vorhersagbarem Schlüsselnamen) - das angeforderte
        # Array steckt dann in irgendeinem Wert des Objekts.
        if isinstance(response, dict):
            response_arr = next((v for v in response.values() if isinstance(v, list)), [])
        else:
            response_arr = response if isinstance(response, list) else []
        reviewed = []
        for r in response_arr:
            if not isinstance(r, dict):
                continue
            idx = r.get("index")
            confidence = r.get("confidence") or 0
            if idx is None or idx < 0 or idx >= len(top_pages):
                continue
            if confidence < min_confidence:
                continue
            chunk, _, link_type = top_pages[idx]
            reviewed.append((chunk, confidence / 100.0, link_type, r.get("reason") or None))
        return reviewed
    except Exception as e:
        logger.warning(
            f"[LinkBuilder] LLM-Review fehlgeschlagen für {entity.name}, verwende ungeprüfte Kandidaten: {e}"
        )
        # Ohne LLM-Urteil ist der heuristische Score (0..1) der einzige Anhaltspunkt —
        # denselben vom Nutzer eingestellten Schwellwert anwenden statt alles durchzureichen,
        # sonst umgeht ein LLM-Ausfall den Regler stillschweigend.
        return [
            (chunk, score, link_type, None)
            for chunk, score, link_type in top_pages
            if round(score * 100) >= min_confidence
        ]


def _entity_content_hash(entity: CodeEntity) -> str:
    """Return a stable fallback for legacy entities without a parser hash."""
    if entity.content_hash:
        return entity.content_hash
    payload = json.dumps(
        {
            "type": entity.type,
            "name": entity.name,
            "file_path": entity.file_path,
            "qualified_name": entity.qualified_name,
            "meta": entity.meta_json or {},
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stamp_link_snapshot(link: EntityDocLink, entity: CodeEntity, chunk: DocumentChunk, model: str) -> None:
    """Persist the exact endpoint state used for one recommendation."""
    link.entity_content_hash = _entity_content_hash(entity)
    link.chunk_content_hash = chunk.content_hash or content_fingerprint(chunk.content or "")
    link.embedding_model = model
    link.entity_link_revision = entity.link_revision or 0
    link.chunk_link_revision = chunk.link_revision or 0


def _is_auto_link(link: EntityDocLink) -> bool:
    return link.created_by == "auto" and link.link_type in {"semantic", "keyword", "syntactic"}


async def compute_entity_links_async(
    run_id: int,
    project_id: int,
    min_confidence: int | None = None,
    embedding_model: str | None = None,
):
    """
    2-pass scan for every CodeEntity in the project:
      Pass 1 — semantic:   cosine similarity via embeddings
      Pass 2 — keyword:    token match of entity name/path against chunk content

    Results are merged (highest score per page wins), kept if the score is above
    MERGE_SCORE_THRESHOLD per entity. Approved/rejected links are never touched.

    run_id points at a LinkBuilderRun row (created by the caller as "pending")
    that this function updates to running/completed/failed — without it, a crash
    here previously only produced a logger.error line with no queryable trace.

    min_confidence (0-100): user-configured minimum LLM confidence (Pass 3) a
    candidate must reach to be saved as a pending recommendation at all — set
    by the user in the Link Manager right before triggering this run. None
    falls back to LLM_MIN_CONFIDENCE (candidate pre-selection in Pass 1+2 is
    intentionally left untouched by this — see docstring at file top).
    """
    effective_min_confidence = LLM_MIN_CONFIDENCE if min_confidence is None else min_confidence
    lock_key = f"lock:compute_entity_links:{project_id}"
    pending_key = f"pending:compute_entity_links:{project_id}"

    db = SessionLocal()
    run = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == run_id).first()
    if not run:
        logger.error(f"[LinkBuilder] LinkBuilderRun {run_id} nicht gefunden — abgebrochen.")
        db.close()
        return
    if run.status == "cancelled":
        logger.info(f"[LinkBuilder] Run {run_id} wurde vor dem Start abgebrochen.")
        db.close()
        return

    selected_embedding_model = (
        embedding_model or run.embedding_model or config.EMBED_MODEL
    ).strip()
    run.embedding_model = selected_embedding_model

    # Try to acquire the Redis lock with run_id as owner, renewed per entity below.
    acquired = redis_client.set(lock_key, str(run_id), ex=LOCK_LEASE_SECONDS, nx=True)
    if not acquired:
        # Check if the lock owner is dead/stale in the database
        current_owner = redis_client.get(lock_key)
        is_stale = False
        if current_owner:
            try:
                owner_run_id = int(current_owner)
                owner_run = (
                    db.query(LinkBuilderRun).filter(LinkBuilderRun.id == owner_run_id).first()
                )
                if not owner_run or owner_run.status in ["completed", "failed", "skipped"]:
                    is_stale = True
            except (ValueError, TypeError):
                is_stale = True

        if is_stale:
            logger.info(
                f"[LinkBuilder] Stale lock found for project {project_id} (owner run {current_owner.decode('utf-8', errors='ignore') if current_owner else 'None'}). Overriding."
            )
            redis_client.delete(lock_key)
            acquired = redis_client.set(lock_key, str(run_id), ex=LOCK_LEASE_SECONDS, nx=True)

    if not acquired:
        logger.info(
            f"[LinkBuilder] Link-Berechnung für Projekt {project_id} läuft bereits. Setze pending flag."
        )
        redis_client.set(pending_key, "true")
        run.status = "skipped"
        run.progress_message = "Es läuft bereits eine Berechnung für dieses Projekt — wird danach automatisch erneut ausgeführt."
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
        return

    # Initialize has_pending to check at the end
    has_pending = False
    try:
        # Clear the pending flag as we are starting now
        redis_client.delete(pending_key)
        run.status = "running"
        db.commit()

        all_entities = db.query(CodeEntity).filter(CodeEntity.project_id == project_id).all()
        if not all_entities:
            logger.info(
                f"[LinkBuilder] Projekt {project_id}: keine Code-Entities gefunden — übersprungen."
            )
            run.status = "completed"
            run.progress_message = "Keine Code-Entities gefunden."
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        doc_count = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.project_id == project_id,
                DocumentChunk.source_id.isnot(None),
                _embedding_model_filter(selected_embedding_model),
            )
            .count()
        )
        if doc_count == 0:
            logger.info(
                f"[LinkBuilder] Projekt {project_id}: keine Wissensquellen — bitte Confluence/Notion synchronisieren."
            )
            run.status = "completed"
            run.progress_message = "Keine Wissensquellen — bitte Confluence/Notion synchronisieren."
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

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
        has_previous_run = (
            db.query(LinkBuilderRun)
            .filter(
                LinkBuilderRun.project_id == project_id,
                LinkBuilderRun.task_type == "entity_links",
                LinkBuilderRun.status == "completed",
                LinkBuilderRun.id != run_id,
            )
            .first()
            is not None
        )
        bootstrap = not dirty_items and not has_previous_run
        dirty_entity_ids = {item.entity_id for item in dirty_items if item.entity_id is not None}
        dirty_chunk_ids = {item.chunk_id for item in dirty_items if item.chunk_id is not None}
        if bootstrap:
            entities = all_entities
            queue_ids: set[int] = set()
            logger.info(
                f"[LinkBuilder] Projekt {project_id}: einmaliger Backfill ({len(entities)} Entities, {doc_count} Chunks)…"
            )
        elif dirty_chunk_ids:
            # A changed chunk may become relevant to any code entity, while an
            # entity-only change can be limited to that entity below.
            entities = all_entities
            queue_ids = {item.id for item in dirty_items}
            logger.info(
                f"[LinkBuilder] Projekt {project_id}: inkrementeller Lauf ({len(dirty_entity_ids)} Entities, {len(dirty_chunk_ids)} Chunks)…"
            )
        else:
            entities = [entity for entity in all_entities if entity.id in dirty_entity_ids]
            queue_ids = {item.id for item in dirty_items}
            logger.info(
                f"[LinkBuilder] Projekt {project_id}: inkrementeller Lauf ({len(entities)} geänderte Entities)…"
            )

        if not entities:
            run.status = "completed"
            run.progress_message = "Keine neuen oder geänderten Link-Kandidaten."
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        # Only pending automatic recommendations are stale work products.
        # Human-created links and approved/rejected decisions are never erased.
        if bootstrap:
            pass
        elif dirty_entity_ids:
            for link in (
                db.query(EntityDocLink)
                .filter(
                    EntityDocLink.project_id == project_id,
                    EntityDocLink.entity_id.in_(dirty_entity_ids),
                    EntityDocLink.status == "pending",
                )
                .all()
            ):
                if _is_auto_link(link):
                    db.delete(link)
        if dirty_chunk_ids:
            for link in (
                db.query(EntityDocLink)
                .filter(
                    EntityDocLink.project_id == project_id,
                    EntityDocLink.chunk_id.in_(dirty_chunk_ids),
                    EntityDocLink.status == "pending",
                )
                .all()
            ):
                if _is_auto_link(link):
                    db.delete(link)
        db.flush()

        await ensure_model_pulled(selected_embedding_model)

        for entity in entities:
            db.refresh(run)
            if run.status == "cancelled":
                logger.info(f"[LinkBuilder] Run {run_id} wurde während der Berechnung abgebrochen.")
                return
            # Heartbeat: renew the lock lease as long as we're still making
            # progress, so a genuinely long-running scan (many entities)
            # never loses its lock mid-run.
            redis_client.expire(lock_key, LOCK_LEASE_SECONDS)

            if not bootstrap and entity.id not in dirty_entity_ids and dirty_chunk_ids:
                candidate_chunk_ids = dirty_chunk_ids
            elif bootstrap or entity.id in dirty_entity_ids:
                candidate_chunk_ids = None
            else:
                continue

            semantic = await _pass_semantic(
                entity, project_id, db, selected_embedding_model, candidate_chunk_ids
            )
            keyword = _pass_keyword(
                entity, project_id, db, selected_embedding_model, candidate_chunk_ids
            )

            top_pages = _merge_passes(
                (semantic, "semantic"),
                (keyword, "keyword"),
            )

            # Optimization: filter out candidates that are already approved or rejected before sending to LLM.
            undecided_pages = []
            for chunk, score, link_type in top_pages:
                already_decided = (
                    db.query(EntityDocLink)
                    .filter(
                        EntityDocLink.entity_id == entity.id,
                        EntityDocLink.chunk_id == chunk.id,
                        EntityDocLink.status.in_(["approved", "rejected"]),
                    )
                    .first()
                )
                if not already_decided:
                    undecided_pages.append((chunk, score, link_type))

            # Only invoke the LLM if there are undecided candidates
            reviewed_pages = []
            if undecided_pages:
                reviewed_pages = await _llm_review(
                    entity, undecided_pages, min_confidence=effective_min_confidence
                )

            for chunk, score, link_type, context in reviewed_pages:
                existing_link = (
                    db.query(EntityDocLink)
                    .filter(
                        EntityDocLink.entity_id == entity.id,
                        EntityDocLink.chunk_id == chunk.id,
                    )
                    .first()
                )
                if existing_link and existing_link.status in {"approved", "rejected"}:
                    continue
                meta = chunk.metadata_json or {}
                link = existing_link
                if link is None:
                    link = EntityDocLink(
                        project_id=project_id,
                        entity_id=entity.id,
                        chunk_id=chunk.id,
                        status="pending",
                        created_by="auto",
                    )
                    db.add(link)
                if _is_auto_link(link) or link.created_by == "auto":
                    link.doc_title = meta.get("title") or chunk.file_path
                    link.doc_url = meta.get("url")
                    link.source_type = meta.get("source_type")
                    link.score = round(score, 4)
                    link.link_type = link_type
                    link.context = context
                    link.status = "pending"
                    _stamp_link_snapshot(link, entity, chunk, selected_embedding_model)

            entity.embedding_model = selected_embedding_model
            for item_id in queue_ids:
                item = db.query(LinkBuilderDirtyItem).filter(LinkBuilderDirtyItem.id == item_id).first()
                if item is not None and (
                    item.entity_id == entity.id
                    or item.chunk_id in (candidate_chunk_ids or set())
                ):
                    db.delete(item)

            db.commit()

        total_new = (
            db.query(EntityDocLink)
            .filter(EntityDocLink.project_id == project_id, EntityDocLink.status == "pending")
            .count()
        )
        logger.info(
            f"[LinkBuilder] Projekt {project_id}: fertig — {total_new} offene Empfehlung(en) gesamt."
        )
        run.status = "completed"
        run.progress_message = f"{total_new} offene Empfehlung(en) gesamt."
        run.links_created = total_new
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        logger.error(f"[LinkBuilder] Fehler für Projekt {project_id}: {e}")
        db.rollback()
        run = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(e)[:500]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
        # Read the pending flag before releasing the lock to prevent race conditions
        has_pending = redis_client.get(pending_key) == b"true"
        if has_pending:
            redis_client.delete(pending_key)

        # Release the lock only if we still own it
        current_owner = redis_client.get(lock_key)
        if current_owner == str(run_id).encode("utf-8"):
            redis_client.delete(lock_key)

        # Trigger re-run if another request arrived during execution
        if has_pending:
            logger.info(
                f"[LinkBuilder] Pending flag für Projekt {project_id} is gesetzt. Starte neuen Durchlauf."
            )
            requeue_db = SessionLocal()
            try:
                new_run = LinkBuilderRun(
                    task_type="entity_links",
                    project_id=project_id,
                    status="pending",
                    progress_message="Erneuter Durchlauf wegen Änderungen während der letzten Berechnung.",
                )
                requeue_db.add(new_run)
                requeue_db.commit()
                requeue_db.refresh(new_run)
                result = current_app.send_task(
                    "compute_entity_links", args=[new_run.id, project_id]
                )
                if getattr(result, "id", None):
                    new_run.celery_task_id = result.id
                    requeue_db.commit()
            finally:
                requeue_db.close()
