"""Hybrid insight candidates: indexed text relevance and matching semantic vectors."""

import asyncio
import concurrent.futures
import logging
import re

from sqlalchemy.orm import defer
from sqlalchemy import func, literal_column
from doctus_models.database import Insight, InsightEmbedding
from doctus_models.insight_workflow import embedding_profile_key
from services.insight_queue import search_vector
import core.config as cfg

logger = logging.getLogger(__name__)


def semantic_candidates(db, project_id, message, *, query_embedding=None, profile_key=None):
    base = (
        db.query(Insight)
        .options(defer(Insight.review_history), defer(Insight.workflow_history))
        .join(InsightEmbedding, Insight.id == InsightEmbedding.insight_id)
        .filter(
            Insight.project_id == project_id,
            Insight.status == "verified",
            Insight.outdated_at.is_(None),
            InsightEmbedding.project_id == project_id,
            InsightEmbedding.content_hash
            == func.encode(
                func.sha256(func.convert_to(Insight.title + "\n" + Insight.content, "UTF8")), "hex"
            ),
        )
    )
    if base.with_entities(Insight.id).first() is None:
        return []
    try:
        from services.answer_context import _embedding_profile_for_project
        from services.ollama_client import embed_text

        profile = _embedding_profile_for_project(db, project_id)
        settings = {
            "provider": profile.provider,
            "model": profile.model,
            "base_url": (profile.base_url or cfg.EMBEDDING_BASE_URL).rstrip("/"),
            "path": profile.path,
            "dimension": profile.dimension,
            "context": profile.context_length,
        }
        expected_key = embedding_profile_key(settings)
        base = base.filter(InsightEmbedding.profile_key == expected_key)
        if base.with_entities(Insight.id).first() is None:
            return []
        if query_embedding is None or profile_key != expected_key:

            async def embed():
                return await asyncio.wait_for(
                    embed_text(
                        message.encode()[:1200].decode("utf-8", errors="ignore"),
                        is_query=True,
                        model=profile.model,
                        provider=profile.provider,
                        base_url=profile.base_url,
                        path=profile.path,
                        api_key=profile.api_key,
                        dimension=profile.dimension,
                        context_length=profile.context_length,
                    ),
                    timeout=3,
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                query_embedding = pool.submit(asyncio.run, embed()).result(timeout=4)
        if len(query_embedding) != 1024:
            return []
        distance = InsightEmbedding.embedding.cosine_distance(query_embedding)
        return base.filter(distance < 0.55).order_by(distance, Insight.id).limit(40).all()
    except Exception as exc:
        logger.info("Insight semantic retrieval unavailable (%s)", type(exc).__name__)
        return []


def ranked_candidates(db, project_id, message, *, query_embedding=None, profile_key=None):
    terms = list(dict.fromkeys(re.findall(r"[^\W_]{3,}", message.lower())))[:12]
    lexical = []
    if terms:
        query = func.websearch_to_tsquery(literal_column("'simple'"), " OR ".join(terms))
        vector = search_vector()
        lexical = (
            db.query(Insight)
            .options(defer(Insight.review_history), defer(Insight.workflow_history))
            .filter(
                Insight.project_id == project_id,
                Insight.status == "verified",
                Insight.outdated_at.is_(None),
                vector.op("@@")(query),
            )
            .order_by(func.ts_rank_cd(vector, query).desc(), Insight.id.desc())
            .limit(40)
            .all()
        )
    semantic = semantic_candidates(
        db, project_id, message, query_embedding=query_embedding, profile_key=profile_key
    )
    scores, by_id = {}, {}
    for channel in (lexical, semantic):
        for rank, row in enumerate(channel):
            by_id[row.id] = row
            scores[row.id] = scores.get(row.id, 0) + 1 / (20 + rank)
    return [by_id[key] for key in sorted(by_id, key=lambda key: (-scores[key], -key))]
