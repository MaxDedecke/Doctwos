"""
parser/tasks/cross_link_builder.py
==================================
Cross-Source Link Analysis:
Computes semantic connections between different knowledge sources and Git repositories.

Logic:
1. Load all DocumentChunks (Confluence, Notion, Jira, Git, etc.)
2. For each chunk: Find nearest neighbors using HNSW index
3. LLM-Review pro Kandidatenpaar: verwirft schwache/falsche Treffer, schreibt eine
   echte Begründung statt des kanonischen "Similarity score: X%"-Strings. Bei
   LLM-Fehler wird der Kandidat mit dem Embedding-Score durchgereicht (kein
   Rauschen-Filter, aber der Scan liefert trotzdem Ergebnisse).
4. Create knowledge_links for top matches across different sources
"""

import asyncio
import logging
from datetime import datetime, timezone
from db import SessionLocal
from models.database import DocumentChunk, KnowledgeLink, CodeEntity, KnowledgeSource, LinkBuilderRun
from ollama_client import get_chat_json
from core import config
from sqlalchemy import or_, and_
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

MIN_SCORE = 0.55
TOP_MATCHES = 5
LLM_MIN_CONFIDENCE = 35


def _chunk_source_label(chunk, db) -> str:
    """
    Menschenlesbares Label für die Herkunft eines DocumentChunk.
    Git-geparste Chunks haben kein KnowledgeSource (source_id ist None) — project_id
    allein reicht seit dem Project-Refactor nicht mehr zur Unterscheidung, da es bei
    jedem projekt-gebundenen Chunk gesetzt ist, egal ob git oder nicht.
    """
    if chunk.source_id is None:
        return "Git"
    source_type = db.query(KnowledgeSource.type).filter(KnowledgeSource.id == chunk.source_id).scalar()
    return source_type or "Local"


async def _llm_review_pair(chunk_a, source_type_a: str, chunk_b, source_type_b: str, heuristic_score: float, min_confidence: int = LLM_MIN_CONFIDENCE) -> dict:
    """Judges one candidate cross-source pair. Never raises — falls back to the heuristic score/canned context on LLM failure."""
    meta_a, meta_b = chunk_a.metadata_json or {}, chunk_b.metadata_json or {}
    title_a = meta_a.get("title") or chunk_a.file_path
    title_b = meta_b.get("title") or chunk_b.file_path
    prompt = (
        "Du bewertest, ob zwei Dokument-Ausschnitte aus unterschiedlichen Quellen wirklich inhaltlich zusammenhängen.\n\n"
        f"Dokument A [{source_type_a}] \"{title_a}\": {(chunk_a.content or '')[:300]}\n\n"
        f"Dokument B [{source_type_b}] \"{title_b}\": {(chunk_b.content or '')[:300]}\n\n"
        "Antworte NUR mit einem JSON-Objekt der Form "
        '{"confidence": <0-100>, "keep": <bool>, "reason": "<kurze Begründung auf Deutsch>"}.'
    )
    try:
        data = await get_chat_json(prompt, config.LLM_MODEL)
        confidence = float(data.get("confidence", 0))
        keep = bool(data.get("keep", False)) and confidence >= min_confidence
        return {"keep": keep, "score": confidence / 100.0, "context": data.get("reason") or None}
    except Exception as e:
        logger.warning(f"[CrossLinkBuilder] LLM-Review fehlgeschlagen, verwende Embedding-Score: {e}")
        # Ohne LLM-Urteil ist der heuristische Score der einzige Anhaltspunkt — denselben
        # vom Nutzer eingestellten Schwellwert anwenden statt immer zu behalten, sonst
        # umgeht ein LLM-Ausfall den Regler stillschweigend.
        return {
            "keep": round(heuristic_score * 100) >= min_confidence,
            "score": heuristic_score,
            "context": f"Similarity score: {round(heuristic_score*100)}%. This content from {source_type_a} and {source_type_b} seems highly related.",
        }

async def compute_knowledge_links_async(run_id: int, min_confidence: int | None = None):
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

    links_created = 0
    try:
        logger.info("[CrossLinkBuilder] Starting cross-source analysis...")
        run.status = "running"
        db.commit()

        # We process chunks that have embeddings
        # For efficiency in a real system, we'd only process "new" or "dirty" chunks
        chunks = db.query(DocumentChunk).filter(DocumentChunk.embedding.isnot(None)).all()
        
        for chunk in chunks:
            # Determine source type and ID for exclusion
            source_id_a = chunk.source_id
            project_id_a = chunk.project_id
            meta_a = chunk.metadata_json or {}
            source_type_a = meta_a.get("source_type") or _chunk_source_label(chunk, db)

            # Find similar chunks from DIFFERENT sources
            dist_expr = DocumentChunk.embedding.cosine_distance(chunk.embedding)
            
            # Query for similar chunks
            query = db.query(DocumentChunk, dist_expr.label("dist")).filter(
                DocumentChunk.id != chunk.id,
                DocumentChunk.embedding.isnot(None)
            )
            
            # Exclude same source
            if source_id_a:
                query = query.filter(DocumentChunk.source_id != source_id_a)
            elif project_id_a:
                query = query.filter(DocumentChunk.project_id != project_id_a)
                
            similar_chunks = (
                query.order_by(dist_expr)
                .limit(TOP_MATCHES)
                .all()
            )
            
            for target_chunk, dist in similar_chunks:
                score = max(0.0, 1.0 - float(dist))
                if score < MIN_SCORE:
                    continue
                
                # Check if link already exists (bidirectional check)
                existing = db.query(KnowledgeLink).filter(
                    or_(
                        and_(KnowledgeLink.source_a_chunk_id == chunk.id, KnowledgeLink.source_b_chunk_id == target_chunk.id),
                        and_(KnowledgeLink.source_a_chunk_id == target_chunk.id, KnowledgeLink.source_b_chunk_id == chunk.id)
                    )
                ).first()
                
                if not existing:
                    meta_b = target_chunk.metadata_json or {}
                    source_type_b = meta_b.get("source_type") or _chunk_source_label(target_chunk, db)

                    review = await _llm_review_pair(chunk, source_type_a, target_chunk, source_type_b, score, min_confidence=effective_min_confidence)
                    if not review["keep"]:
                        continue

                    # Try to find an entity if this is a code file
                    entity_a = None
                    if project_id_a:
                        entity_a = db.query(CodeEntity).filter(
                            CodeEntity.project_id == project_id_a,
                            CodeEntity.file_path == chunk.file_path,
                            CodeEntity.start_line <= chunk.start_line,
                            CodeEntity.end_line >= chunk.end_line
                        ).first()

                    entity_b = None
                    if target_chunk.project_id:
                        entity_b = db.query(CodeEntity).filter(
                            CodeEntity.project_id == target_chunk.project_id,
                            CodeEntity.file_path == target_chunk.file_path,
                            CodeEntity.start_line <= target_chunk.start_line,
                            CodeEntity.end_line >= target_chunk.end_line
                        ).first()

                    db.add(KnowledgeLink(
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
                        context=review["context"]
                    ))
                    links_created += 1
            db.commit()

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
