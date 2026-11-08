"""Refresh a bounded batch of approved insight vectors on the existing worker."""

import asyncio
import logging
from time import monotonic
from datetime import datetime, timezone
from sqlalchemy.orm import defer
from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert

from db import SessionLocal
from doctus_models.database import Insight, InsightEmbedding
from doctus_models.insight_workflow import embedding_profile_key, embedding_text, content_hash
from ollama_client import _effective_embedding_settings, _get_embeddings_sub_batch

logger = logging.getLogger(__name__)


async def refresh_insight_embeddings(limit=25):
    try:
        settings = _effective_embedding_settings()
    except Exception:
        return {"updated": 0, "unavailable": True}
    settings = {**settings, "base_url": settings["base_url"].rstrip("/")}
    key = embedding_profile_key(settings)
    with SessionLocal() as db:
        sql_hash = func.encode(
            func.sha256(func.convert_to(Insight.title + "\n" + Insight.content, "UTF8")), "hex"
        )
        rows = (
            db.query(Insight)
            .options(defer(Insight.review_history), defer(Insight.workflow_history))
            .outerjoin(InsightEmbedding, Insight.id == InsightEmbedding.insight_id)
            .filter(
                Insight.status == "verified",
                Insight.outdated_at.is_(None),
                or_(
                    InsightEmbedding.insight_id.is_(None),
                    InsightEmbedding.profile_key != key,
                    InsightEmbedding.content_hash != sql_hash,
                ),
            )
            .order_by(Insight.id)
            .limit(min(limit, 25))
            .all()
        )
        batch = [
            (
                i.id,
                i.project_id,
                content_hash(i),
                embedding_text(i, max(1, settings["context"] - 40)),
            )
            for i in rows
        ]
    updated, failed, started = 0, 0, monotonic()
    for insight_id, project_id, digest, text in batch:
        if monotonic() - started > 90:
            break
        if settings["model"].startswith("nomic-embed-text"):
            text = "search_document: " + text
        try:
            vectors = await asyncio.wait_for(
                _get_embeddings_sub_batch(
                    [text],
                    settings["model"],
                    1,
                    settings,
                ),
                timeout=10,
            )
            with SessionLocal() as db:
                current = (
                    db.query(Insight)
                    .options(defer(Insight.review_history), defer(Insight.workflow_history))
                    .filter_by(id=insight_id, project_id=project_id)
                    .with_for_update()
                    .first()
                )
                if (
                    current is None
                    or current.status != "verified"
                    or content_hash(current) != digest
                ):
                    continue
                db.execute(
                    insert(InsightEmbedding)
                    .values(
                        insight_id=insight_id,
                        project_id=project_id,
                        profile_key=key,
                        content_hash=digest,
                        embedding=vectors[0],
                        updated_at=datetime.now(timezone.utc),
                    )
                    .on_conflict_do_update(
                        index_elements=["insight_id"],
                        set_={
                            "profile_key": key,
                            "content_hash": digest,
                            "embedding": vectors[0],
                            "updated_at": datetime.now(timezone.utc),
                        },
                    )
                )
                db.commit()
                updated += 1
        except Exception as exc:
            failed += 1
            logger.info("Insight embedding refresh unavailable (%s)", type(exc).__name__)
    return {"updated": updated, "failed": failed}
