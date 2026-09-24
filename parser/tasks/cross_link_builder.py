"""
parser/tasks/cross_link_builder.py
==================================
Cross-Source Link Analysis:
Computes semantic connections between different knowledge sources and Git repositories.

Logic:
1. Load all DocumentChunks (Confluence, Notion, Jira, Git, etc.)
2. For each chunk: Find nearest neighbors using HNSW index
3. LLM-Review pro Kandidatenpaar: nur begründete Treffer werden gespeichert.
4. Create knowledge_links for top matches across different sources
"""

import logging
from datetime import datetime, timezone
from db import SessionLocal
from models.database import (
    DocumentChunk,
    KnowledgeLink,
    CodeEntity,
    KnowledgeSource,
    LinkBuilderRun,
)
from ollama_client import get_chat_json
from core import config
from sqlalchemy import or_, and_

logger = logging.getLogger(__name__)

MIN_SCORE = 0.55
TOP_MATCHES = 5
LLM_MIN_CONFIDENCE = 35


def _embedding_model_filter(model: str):
    if model == config.EMBED_MODEL:
        return or_(DocumentChunk.embedding_model == model, DocumentChunk.embedding_model.is_(None))
    return DocumentChunk.embedding_model == model


def _chunk_source_label(chunk, db) -> str:
    """
    Menschenlesbares Label für die Herkunft eines DocumentChunk.
    Git-geparste Chunks haben kein KnowledgeSource (source_id ist None) — project_id
    allein reicht seit dem Project-Refactor nicht mehr zur Unterscheidung, da es bei
    jedem projekt-gebundenen Chunk gesetzt ist, egal ob git oder nicht.
    """
    if chunk.source_id is None:
        return "Git"
    source_type = (
        db.query(KnowledgeSource.type).filter(KnowledgeSource.id == chunk.source_id).scalar()
    )
    return source_type or "Local"


async def _llm_review_pair(
    chunk_a,
    source_type_a: str,
    chunk_b,
    source_type_b: str,
    heuristic_score: float,
    min_confidence: int = LLM_MIN_CONFIDENCE,
) -> dict:
    """Judge one pair; an embedding score alone never establishes a link."""
    meta_a, meta_b = chunk_a.metadata_json or {}, chunk_b.metadata_json or {}
    title_a = meta_a.get("title") or chunk_a.file_path
    title_b = meta_b.get("title") or chunk_b.file_path
    prompt = (
        "Du bewertest, ob zwei Dokument-Ausschnitte aus unterschiedlichen Quellen wirklich inhaltlich zusammenhängen.\n\n"
        f'Dokument A [{source_type_a}] "{title_a}": {(chunk_a.content or "")[:900]}\n\n'
        f'Dokument B [{source_type_b}] "{title_b}": {(chunk_b.content or "")[:900]}\n\n'
        "Beschreibe den konkreten gemeinsamen Sachverhalt und welche Details aus A und B ihn belegen. "
        "Benenne Unsicherheit oder Widersprüche. Gib keine bloße Ähnlichkeitsaussage zurück.\n"
        "Antworte NUR mit einem JSON-Objekt der Form "
        '{"confidence": <0-100>, "keep": <bool>, "reason": "<konkrete Begründung in 2-4 Sätzen auf Deutsch>"}.'
    )
    try:
        data = await get_chat_json(prompt, config.LLM_MODEL)
        confidence = float(data.get("confidence", 0))
        reason = str(data.get("reason") or "").strip()
        keep = bool(data.get("keep", False)) and confidence >= min_confidence
        if keep and len(reason) < 40:
            raise ValueError("LLM lieferte für einen bestätigten Kandidaten keine konkrete Begründung")
        return {"keep": keep, "score": confidence / 100.0, "context": reason or None}
    except Exception as e:
        raise RuntimeError(f"LLM-Prüfung für Cross-Source-Kandidat fehlgeschlagen: {e}") from e


async def compute_knowledge_links_async(
    run_id: int,
    min_confidence: int | None = None,
    embedding_model: str | None = None,
    project_id: int | None = None,
    source_ids: list[int] | None = None,
):
    """
    run_id points at a LinkBuilderRun row (created by the caller as "pending",
    task_type="knowledge_links", project_id=None since this scans across all
    projects/sources) that this function updates to running/completed/failed —
    without it, a crash here previously only produced a logger.error line with
    no queryable trace.

    min_confidence (0-100): user-configured minimum LLM confidence a candidate
    pair must reach to be saved as a pending link — set by the user in the
    Link Manager right before triggering this run. None falls back to
    LLM_MIN_CONFIDENCE (candidate pre-selection via MIN_SCORE stays untouched).
    """
    effective_min_confidence = LLM_MIN_CONFIDENCE if min_confidence is None else min_confidence
    db = SessionLocal()
    run = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == run_id).first()
    if not run:
        logger.error(f"[CrossLinkBuilder] LinkBuilderRun {run_id} nicht gefunden — abgebrochen.")
        db.close()
        return
    if run.status != "pending":
        logger.info(
            "[CrossLinkBuilder] Run %s ist bereits %s und wird nicht gestartet.",
            run_id,
            run.status,
        )
        db.close()
        return

    scope = run.scope_json or {}
    selected_project_id = project_id or scope.get("project_id") or run.project_id
    selected_source_ids = sorted(set(source_ids or scope.get("source_ids") or []))
    if not selected_project_id or len(selected_source_ids) < 2:
        run.status = "failed"
        run.error_message = "Cross-Source-Lauf ohne verpflichtenden Projekt- und Quellen-Scope."
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.close()
        return
    run.project_id = selected_project_id
    run.scope_json = {**scope, "project_id": selected_project_id, "source_ids": selected_source_ids}

    selected_embedding_model = (
        embedding_model or run.embedding_model or config.EMBED_MODEL
    ).strip()
    run.embedding_model = selected_embedding_model

    links_created = int(run.links_created or 0)
    try:
        logger.info("[CrossLinkBuilder] Starting cross-source analysis...")
        run.status = "running"
        db.commit()

        # We process chunks that have embeddings
        # For efficiency in a real system, we'd only process "new" or "dirty" chunks
        model_filter = _embedding_model_filter(selected_embedding_model)
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.project_id == selected_project_id,
            DocumentChunk.source_id.in_(selected_source_ids),
            DocumentChunk.embedding.isnot(None), model_filter
        ).order_by(DocumentChunk.id).all()

        scope = dict(run.scope_json or {})
        resume_after_id = int(scope.get("resume_after_id") or 0)
        chunks = [chunk for chunk in chunks if chunk.id > resume_after_id]
        processed_before = int(scope.get("processed_items") or 0) if resume_after_id else 0
        max_items = max(1, min(5000, int(scope.get("max_items") or 200)))
        total_items = int(scope.get("total_items") or len(chunks)) if resume_after_id else len(chunks)
        scope.update(total_items=total_items, processed_items=processed_before, max_items=max_items)
        run.scope_json = scope
        run.progress_message = f"{processed_before} von {total_items} Dokument-Abschnitten geprüft (Budget: {max_items})."
        db.commit()

        for processed_index, chunk in enumerate(chunks, start=1):
            db.refresh(run)
            if run.status == "cancelled":
                logger.info("[CrossLinkBuilder] Run %s abgebrochen.", run_id)
                return
            # Determine source type and ID for exclusion
            source_id_a = chunk.source_id
            project_id_a = chunk.project_id
            meta_a = chunk.metadata_json or {}
            source_type_a = meta_a.get("source_type") or _chunk_source_label(chunk, db)

            # Find similar chunks from DIFFERENT sources
            dist_expr = DocumentChunk.embedding.cosine_distance(chunk.embedding)

            # Query for similar chunks
            query = db.query(DocumentChunk, dist_expr.label("dist")).filter(
                DocumentChunk.project_id == selected_project_id,
                DocumentChunk.source_id.in_(selected_source_ids),
                DocumentChunk.id != chunk.id,
                DocumentChunk.embedding.isnot(None),
                model_filter,
            )

            # Exclude same source
            if source_id_a:
                query = query.filter(DocumentChunk.source_id != source_id_a)
            elif project_id_a:
                query = query.filter(DocumentChunk.project_id != project_id_a)

            similar_chunks = query.order_by(dist_expr).limit(TOP_MATCHES).all()

            for target_chunk, dist in similar_chunks:
                score = max(0.0, 1.0 - float(dist))
                if score < MIN_SCORE:
                    continue

                # Check if link already exists (bidirectional check)
                existing = (
                    db.query(KnowledgeLink)
                    .filter(
                        or_(
                            and_(
                                KnowledgeLink.source_a_chunk_id == chunk.id,
                                KnowledgeLink.source_b_chunk_id == target_chunk.id,
                            ),
                            and_(
                                KnowledgeLink.source_a_chunk_id == target_chunk.id,
                                KnowledgeLink.source_b_chunk_id == chunk.id,
                            ),
                        )
                    )
                    .first()
                )

                if not existing:
                    meta_b = target_chunk.metadata_json or {}
                    source_type_b = meta_b.get("source_type") or _chunk_source_label(
                        target_chunk, db
                    )

                    review = await _llm_review_pair(
                        chunk,
                        source_type_a,
                        target_chunk,
                        source_type_b,
                        score,
                        min_confidence=effective_min_confidence,
                    )
                    if not review["keep"]:
                        continue

                    # Try to find an entity if this is a code file
                    entity_a = None
                    if project_id_a:
                        entity_a = (
                            db.query(CodeEntity)
                            .filter(
                                CodeEntity.project_id == project_id_a,
                                CodeEntity.file_path == chunk.file_path,
                                CodeEntity.start_line <= chunk.start_line,
                                CodeEntity.end_line >= chunk.end_line,
                            )
                            .first()
                        )

                    entity_b = None
                    if target_chunk.project_id:
                        entity_b = (
                            db.query(CodeEntity)
                            .filter(
                                CodeEntity.project_id == target_chunk.project_id,
                                CodeEntity.file_path == target_chunk.file_path,
                                CodeEntity.start_line <= target_chunk.start_line,
                                CodeEntity.end_line >= target_chunk.end_line,
                            )
                            .first()
                        )

                    db.add(
                        KnowledgeLink(
                            source_a_type="entity" if entity_a else "document",
                            source_a_entity_id=entity_a.id if entity_a else None,
                            source_a_chunk_id=chunk.id,
                            source_a_title=meta_a.get("title") or chunk.file_path,
                            source_a_url=meta_a.get("url"),
                            source_a_source_type=source_type_a,
                            source_b_type="entity" if entity_b else "document",
                            source_b_entity_id=entity_b.id if entity_b else None,
                            source_b_chunk_id=target_chunk.id,
                            source_b_title=meta_b.get("title") or target_chunk.file_path,
                            source_b_url=meta_b.get("url"),
                            source_b_source_type=source_type_b,
                            score=round(review["score"], 4),
                            link_type="semantic",
                            status="pending",
                            context=review["context"],
                        )
                    )
                    links_created += 1
            scope = dict(run.scope_json or {})
            overall_processed = processed_before + processed_index
            scope.update(processed_items=overall_processed, resume_after_id=chunk.id)
            run.scope_json = scope
            run.progress_message = f"{overall_processed} von {total_items} Dokument-Abschnitten geprüft (Budget: {max_items})."
            db.commit()
            if processed_index >= max_items and overall_processed < total_items:
                run.status = "cancelled"
                run.progress_message = f"Budget nach {overall_processed} von {total_items} Abschnitten erreicht; im Job Center fortsetzen."
                run.links_created = links_created
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
                return

        logger.info("[CrossLinkBuilder] Cross-source analysis finished.")
        run.status = "completed"
        run.progress_message = f"{links_created} neue Knowledge-Link(s) erstellt."
        run.links_created = links_created
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        logger.error(f"[CrossLinkBuilder] Error: {e}")
        db.rollback()
        run = db.query(LinkBuilderRun).filter(LinkBuilderRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(e)[:500]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
