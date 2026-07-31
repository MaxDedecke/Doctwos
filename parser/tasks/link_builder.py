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
Link-Manager-Frontend angezeigt wird.

Pass 3 — LLM-Review:  Ein LLM-Call pro Entity bewertet die gemergten Kandidaten,
                       verwirft schwache/falsche Treffer und schreibt eine echte
                       Begründung (EntityDocLink.context). Ersetzt den Heuristik-
                       Score durch die LLM-Konfidenz. Kein Auto-Approve — die
                       Links landen weiterhin als "pending" im Review-Workflow.

Nur "approved" Links werden vom Agent und Monaco-Tooltips verwendet.
Bestehende approved/rejected Links werden nie überschrieben.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from db import SessionLocal, REDIS_URL
from models.database import CodeEntity, DocumentChunk, EntityDocLink, LinkBuilderRun
from ollama_client import get_embedding, get_chat_json, ensure_model_pulled
from core import config
import redis
from celery import current_app

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
TOP_PAGES = 5
LLM_MIN_CONFIDENCE = 35


def _keywords_from_entity(entity: CodeEntity) -> list[str]:
    tokens = re.split(r'[-_]', entity.name)
    tokens += re.split(r'[-_]', os.path.splitext(os.path.basename(entity.file_path))[0])
    seen, result = set(), []
    for t in tokens:
        t = t.lower()
        if len(t) >= 3 and t not in seen:
            seen.add(t)
            result.append(t)
    return result


async def _pass_semantic(entity: CodeEntity, project_id: int, db) -> dict[str, tuple]:
    """Pass 1: cosine similarity between entity context and doc chunk embeddings."""
    context = f"{entity.type}: {entity.name} in {entity.file_path}"
    try:
        embedding = await get_embedding(context, model=config.EMBED_MODEL)
    except Exception as e:
        logger.error(f"[LinkBuilder] Embedding failed for {entity.name}: {e}")
        return {}

    dist_expr = DocumentChunk.embedding.cosine_distance(embedding)
    rows = (
        db.query(DocumentChunk, dist_expr.label("dist"))
        .filter(DocumentChunk.project_id == project_id, DocumentChunk.source_id.isnot(None))
        .order_by(dist_expr)
        .limit(TOP_CHUNKS_SEMANTIC)
        .all()
    )

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


def _pass_keyword(entity: CodeEntity, project_id: int, db) -> dict[str, tuple]:
    """Pass 2: token-based search — splits entity name/path and matches against chunk content.

    DocumentChunk.content is Fernet-encrypted at rest (EncryptedString), so this can no longer
    filter with SQL ILIKE -- candidates are fetched by the existing project_id/source_id scope
    and matched against the keywords in Python after decryption instead.
    """
    keywords = _keywords_from_entity(entity)
    if not keywords:
        return {}

    candidates = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.project_id == project_id, DocumentChunk.source_id.isnot(None))
        .all()
    )

    result: dict[str, tuple] = {}
    matched_chunks = 0
    for chunk in candidates:
        content_lower = (chunk.content or '').lower()
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
    return sorted_pages[:TOP_PAGES]


async def _llm_review(entity: CodeEntity, top_pages: list[tuple[DocumentChunk, float, str]]) -> list[tuple[DocumentChunk, float, str, str]]:
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
        "    \"index\": 0,\n"
        "    \"confidence\": 85, // Ganzzahl 0-100, wie sicher bist du bezüglich der Relevanz\n"
        "    \"reason\": \"Erkläre kurz in 1-2 Sätzen, warum diese Doku für die Entity wichtig ist.\"\n"
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
            if confidence < LLM_MIN_CONFIDENCE:
                continue
            chunk, _, link_type = top_pages[idx]
            reviewed.append((chunk, confidence / 100.0, link_type, r.get("reason") or None))
        return reviewed
    except Exception as e:
        logger.warning(f"[LinkBuilder] LLM-Review fehlgeschlagen für {entity.name}, verwende ungeprüfte Kandidaten: {e}")
        return [(chunk, score, link_type, None) for chunk, score, link_type in top_pages]


async def compute_entity_links_async(run_id: int, project_id: int):
    """
    2-pass scan for every CodeEntity in the project:
      Pass 1 — semantic:   cosine similarity via embeddings
      Pass 2 — keyword:    token match of entity name/path against chunk content

    Results are merged (highest score per page wins), capped at TOP_PAGES per entity.
    Approved/rejected links are never touched.

    run_id points at a LinkBuilderRun row (created by the caller as "pending")
    that this function updates to running/completed/failed — without it, a crash
    here previously only produced a logger.error line with no queryable trace.
    """
    lock_key = f"lock:compute_entity_links:{project_id}"
    pending_key = f"pending:compute_entity_links:{project_id}"

    db = SessionLocal()
    run = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == run_id).first()
    if not run:
        logger.error(f"[LinkBuilder] LinkBuilderRun {run_id} nicht gefunden — abgebrochen.")
        db.close()
        return

    # Try to acquire the Redis lock with run_id as owner, renewed per entity below.
    acquired = redis_client.set(lock_key, str(run_id), ex=LOCK_LEASE_SECONDS, nx=True)
    if not acquired:
        # Check if the lock owner is dead/stale in the database
        current_owner = redis_client.get(lock_key)
        is_stale = False
        if current_owner:
            try:
                owner_run_id = int(current_owner)
                owner_run = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == owner_run_id).first()
                if not owner_run or owner_run.status in ["completed", "failed", "skipped"]:
                    is_stale = True
            except (ValueError, TypeError):
                is_stale = True
        
        if is_stale:
            logger.info(f"[LinkBuilder] Stale lock found for project {project_id} (owner run {current_owner.decode('utf-8', errors='ignore') if current_owner else 'None'}). Overriding.")
            redis_client.delete(lock_key)
            acquired = redis_client.set(lock_key, str(run_id), ex=LOCK_LEASE_SECONDS, nx=True)

    if not acquired:
        logger.info(f"[LinkBuilder] Link-Berechnung für Projekt {project_id} läuft bereits. Setze pending flag.")
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

        entities = db.query(CodeEntity).filter(CodeEntity.project_id == project_id).all()
        if not entities:
            logger.info(f"[LinkBuilder] Projekt {project_id}: keine Code-Entities gefunden — übersprungen.")
            run.status = "completed"
            run.progress_message = "Keine Code-Entities gefunden."
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        doc_count = db.query(DocumentChunk).filter(
            DocumentChunk.project_id == project_id,
            DocumentChunk.source_id.isnot(None)
        ).count()
        if doc_count == 0:
            logger.info(f"[LinkBuilder] Projekt {project_id}: keine Wissensquellen — bitte Confluence/Notion synchronisieren.")
            run.status = "completed"
            run.progress_message = "Keine Wissensquellen — bitte Confluence/Notion synchronisieren."
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        logger.info(f"[LinkBuilder] Projekt {project_id}: starte 3-Pass-Scan ({len(entities)} Entities, {doc_count} Chunks)…")
        await ensure_model_pulled(config.EMBED_MODEL)

        for entity in entities:
            # Heartbeat: renew the lock lease as long as we're still making
            # progress, so a genuinely long-running scan (many entities)
            # never loses its lock mid-run.
            redis_client.expire(lock_key, LOCK_LEASE_SECONDS)

            semantic = await _pass_semantic(entity, project_id, db)
            keyword = _pass_keyword(entity, project_id, db)

            top_pages = _merge_passes(
                (semantic, "semantic"),
                (keyword, "keyword"),
            )

            # Optimization: filter out candidates that are already approved or rejected before sending to LLM.
            undecided_pages = []
            for chunk, score, link_type in top_pages:
                already_decided = db.query(EntityDocLink).filter(
                    EntityDocLink.entity_id == entity.id,
                    EntityDocLink.chunk_id == chunk.id,
                    EntityDocLink.status.in_(["approved", "rejected"])
                ).first()
                if not already_decided:
                    undecided_pages.append((chunk, score, link_type))

            # Only invoke the LLM if there are undecided candidates
            reviewed_pages = []
            if undecided_pages:
                reviewed_pages = await _llm_review(entity, undecided_pages)

            db.query(EntityDocLink).filter(
                EntityDocLink.entity_id == entity.id,
                # "syntactic" no longer produced (Pass 3 removed) but still cleared
                # here so any pre-existing pending suggestions of that type from
                # before this change don't linger forever unreviewed.
                EntityDocLink.link_type.in_(["semantic", "keyword", "syntactic"]),
                EntityDocLink.status == "pending"
            ).delete(synchronize_session=False)

            for chunk, score, link_type, context in reviewed_pages:
                # Double check to prevent duplicate insertion
                already_decided = db.query(EntityDocLink).filter(
                    EntityDocLink.entity_id == entity.id,
                    EntityDocLink.chunk_id == chunk.id,
                    EntityDocLink.status.in_(["approved", "rejected"])
                ).first()
                if already_decided:
                    continue
                meta = chunk.metadata_json or {}
                db.add(EntityDocLink(
                    project_id=project_id,
                    entity_id=entity.id,
                    chunk_id=chunk.id,
                    doc_title=meta.get("title") or chunk.file_path,
                    doc_url=meta.get("url"),
                    source_type=meta.get("source_type"),
                    score=round(score, 4),
                    link_type=link_type,
                    context=context,
                    status="pending",
                    created_by="auto"
                ))

            db.commit()

        total_new = db.query(EntityDocLink).filter(
            EntityDocLink.project_id == project_id,
            EntityDocLink.status == "pending"
        ).count()
        logger.info(f"[LinkBuilder] Projekt {project_id}: fertig — {total_new} offene Empfehlung(en) gesamt.")
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
            logger.info(f"[LinkBuilder] Pending flag für Projekt {project_id} is gesetzt. Starte neuen Durchlauf.")
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
                current_app.send_task("compute_entity_links", args=[new_run.id, project_id])
            finally:
                requeue_db.close()
