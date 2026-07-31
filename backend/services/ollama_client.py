"""
backend/services/ollama_client.py
==================================
Geteilte Ollama-Aufrufe für die AEC-Agenten (compliance, hoai).
Fasst zwei bisher pro Router duplizierte Muster zusammen: die Embedding-Suche aus
api/chat.py:230-285 / api/link_chat.py:104-129, und den Single-Shot-JSON-LLM-Call
im Stil von parser/ollama_client.py:get_chat_json (dortiger Parser-Service, hier
für den Backend-Service nachgebaut, da Container getrennt sind).

Wichtig: Modul-Import wie in api/system.py beschrieben ("import core.config as cfg"),
damit zur Laufzeit über POST /model-info geänderte Modelle sofort greifen.
"""

import json
import logging
from typing import Optional

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

import core.config as cfg
from models.database import DocumentChunk, KnowledgeSource

logger = logging.getLogger(__name__)


async def embed_text(text: str, is_query: bool = True) -> list[float]:
    """Erzeugt ein Embedding via Ollama. nomic-embed-text braucht ein Prefix
    ("search_query:"/"search_document:"), damit Anfragen und Dokumente sauber
    getrennt kodiert werden (siehe api/chat.py:234-236)."""
    prompt = text
    if cfg.OLLAMA_EMBED_MODEL.startswith("nomic-embed-text") and not text.startswith(
        ("search_query:", "search_document:")
    ):
        prefix = "search_query: " if is_query else "search_document: "
        prompt = f"{prefix}{text}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{cfg.OLLAMA_BASE_URL}/api/embeddings",
            json={"model": cfg.OLLAMA_EMBED_MODEL, "prompt": prompt},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]


async def search_project_chunks(
    db: Session,
    project_id: int,
    query: str,
    limit: int = 6,
    metadata_filters: Optional[dict] = None,
    max_distance: Optional[float] = None,
) -> list[DocumentChunk]:
    """Embeddet `query` und liefert die nächsten DocumentChunks für ein Projekt
    (=project_id): Chunks mit project_id==project_id ODER source_id einer KnowledgeSource
    dieses Projekts.

    metadata_filters: Exact-Match-Filter auf metadata_json (z.B. {"element_type": "ifc_wall"}).
    max_distance: verwirft Treffer, deren Cosine-Distance darüber liegt — pgvector
    liefert sonst immer die "nächsten" Chunks, egal wie irrelevant sie tatsächlich sind.
    """
    query_embedding = await embed_text(query, is_query=True)

    source_ids = [
        s.id for s in db.query(KnowledgeSource.id).filter(KnowledgeSource.project_id == project_id).all()
    ]
    filters = [DocumentChunk.project_id == project_id]
    if source_ids:
        filters.append(DocumentChunk.source_id.in_(source_ids))

    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    # Größerer Kandidatenpool, falls danach noch in Python gefiltert wird
    # (pgvector kennt keine nativen Filter auf JSON-Metadaten kombiniert mit Vektor-Sortierung).
    pool_size = limit * 4 if (metadata_filters or max_distance is not None) else limit

    rows = (
        db.query(DocumentChunk, distance.label("distance"))
        .filter(or_(*filters))
        .order_by(distance)
        .limit(pool_size)
        .all()
    )

    out = []
    for chunk, dist in rows:
        if max_distance is not None and dist > max_distance:
            continue
        if metadata_filters:
            meta = chunk.metadata_json or {}
            if not all(meta.get(k) == v for k, v in metadata_filters.items()):
                continue
        out.append(chunk)
        if len(out) >= limit:
            break
    return out


async def ask_llm_json(prompt: str, model: Optional[str] = None, timeout: float = 60.0) -> dict:
    """Single-Shot-LLM-Aufruf über Ollamas natives /api/chat mit format="json" —
    liefert auch bei kleinen lokalen Modellen (z.B. mistral-nemo) zuverlässig
    strukturierte Ausgabe. Wirft bei HTTP-/JSON-Fehlern; Aufrufer entscheiden
    über das Fallback-Verhalten."""
    model_to_use = cfg.resolve_ollama_model(model)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{cfg.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model_to_use,
                "messages": [{"role": "user", "content": prompt}],
                "format": "json",
                "stream": False,
            },
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return json.loads(content)
