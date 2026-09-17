"""
backend/services/ollama_client.py
==================================
Geteilte Ollama-Aufrufe für die AEC-Agenten (compliance, hoai).
Fasst ein bisher pro Router dupliziertes Muster zusammen: die Embedding-Suche aus
api/chat.py:230-285 (vormals auch api/link_chat.py, entfernt mit O-115 als toter
Endpunkt), und den Single-Shot-JSON-LLM-Call im Stil von
parser/ollama_client.py:get_chat_json (dortiger Parser-Service, hier für den
Backend-Service nachgebaut, da Container getrennt sind).

Wichtig: Modul-Import wie in api/system.py beschrieben ("import core.config as cfg"),
damit zur Laufzeit über POST /model-info geänderte Modelle sofort greifen.
"""

import json
import logging
import re
from typing import Optional

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

import core.config as cfg
from models.database import DocumentChunk, KnowledgeSource

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> dict:
    """Parst ein JSON-Objekt aus einer LLM-Textantwort, die (anders als Ollamas
    format="json" oder OpenAIs response_format=json_object) in einen ```json
    ...```-Codeblock verpackt sein kann — bei Gemini/Anthropic beobachtet, die
    kein natives JSON-Erzwingen für diesen einfachen Single-Shot-Call kennen."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.MULTILINE
        )
    return json.loads(cleaned)


async def embed_text(
    text: str,
    is_query: bool = True,
    model: Optional[str] = None,
    *,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    path: Optional[str] = None,
    api_key: Optional[str] = None,
    dimension: Optional[int] = None,
    context_length: Optional[int] = None,
) -> list[float]:
    """Erzeugt ein Embedding via Ollama. nomic-embed-text braucht ein Prefix
    ("search_query:"/"search_document:"), damit Anfragen und Dokumente sauber
    getrennt kodiert werden (siehe api/chat.py:234-236)."""
    embedding_model = (model or cfg.OLLAMA_EMBED_MODEL).strip()
    prompt = text
    if embedding_model.startswith("nomic-embed-text") and not text.startswith(
        ("search_query:", "search_document:")
    ):
        prefix = "search_query: " if is_query else "search_document: "
        prompt = f"{prefix}{text}"

    selected_provider = (provider or cfg.EMBEDDING_PROVIDER).lower()
    selected_base = (base_url or cfg.EMBEDDING_BASE_URL).rstrip("/")
    selected_key = cfg.EMBEDDING_API_KEY if api_key is None else api_key
    headers = {"Content-Type": "application/json"}
    if selected_key:
        headers["Authorization"] = f"Bearer {selected_key}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        if selected_provider == "openai":
            resp = await client.post(
                f"{selected_base}/{(path or '/embeddings').lstrip('/')}",
                json={"model": embedding_model, "input": prompt},
                headers=headers,
            )
            resp.raise_for_status()
            embedding = resp.json()["data"][0]["embedding"]
        elif selected_provider == "ollama":
            resp = await client.post(
                f"{selected_base}/{(path or '/api/embed').lstrip('/')}",
                json={
                    "model": embedding_model,
                    "input": prompt,
                    "dimensions": dimension or cfg.EMBEDDING_DIMENSION,
                    "options": {"num_ctx": context_length or cfg.EMBEDDING_CONTEXT_LENGTH},
                },
                headers=headers,
            )
            resp.raise_for_status()
            embedding = resp.json()["embeddings"][0]
        else:
            raise ValueError(
                f"EMBEDDING_PROVIDER muss 'ollama' oder 'openai' sein, nicht {selected_provider!r}."
            )
        return embedding


async def search_project_chunks(
    db: Session,
    project_id: int,
    query: str,
    limit: int = 6,
    metadata_filters: Optional[dict] = None,
    max_distance: Optional[float] = None,
    embedding_model: Optional[str] = None,
) -> list[DocumentChunk]:
    """Embeddet `query` und liefert die nächsten DocumentChunks für ein Projekt
    (=project_id): Chunks mit project_id==project_id ODER source_id einer KnowledgeSource
    dieses Projekts.

    metadata_filters: Exact-Match-Filter auf metadata_json (z.B. {"element_type": "ifc_wall"}).
    max_distance: verwirft Treffer, deren Cosine-Distance darüber liegt — pgvector
    liefert sonst immer die "nächsten" Chunks, egal wie irrelevant sie tatsächlich sind.
    """
    query_embedding = await embed_text(query, is_query=True, model=embedding_model)

    source_ids = [
        s.id
        for s in db.query(KnowledgeSource.id).filter(KnowledgeSource.project_id == project_id).all()
    ]
    filters = [DocumentChunk.project_id == project_id]
    if source_ids:
        filters.append(DocumentChunk.source_id.in_(source_ids))
    selected_model = (embedding_model or cfg.OLLAMA_EMBED_MODEL).strip()
    if selected_model == cfg.OLLAMA_EMBED_MODEL:
        filters.append(
            or_(
                DocumentChunk.embedding_model == selected_model,
                DocumentChunk.embedding_model.is_(None),
            )
        )
    else:
        filters.append(DocumentChunk.embedding_model == selected_model)

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
    über das Fallback-Verhalten. Dünner Ollama-only-Wrapper um
    ask_llm_json_for_profile() unten."""
    return await ask_llm_json_for_profile(prompt, provider="ollama", model=model, timeout=timeout)


async def ask_llm_json_for_profile(
    prompt: str,
    provider: Optional[str] = "ollama",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = 60.0,
    protocol: Optional[str] = None,
    path: Optional[str] = None,
) -> dict:
    """Single-Shot-JSON-LLM-Aufruf für ein beliebiges LLM-Profil (lokales Ollama
    oder Cloud-Opt-in OpenAI/Gemini/Anthropic) — Provider-Dispatch analog
    api/chat.py, hier Non-Streaming-JSON für Einzel-Bewertungen wie
    entity_links.py::llm_review_link.

    WICHTIG: Aufrufer MUSS für provider in cfg.CLOUD_LLM_PROVIDERS vorher
    cfg.cloud_llm_allowed() prüfen (siehe core/config.py-Kommentar zum Gate) —
    diese Funktion selbst prüft es nicht, damit sie auch aus einem Kontext ohne
    HTTPException-Semantik (z.B. Celery-Task) nutzbar bleibt.
    """
    provider = (provider or "ollama").lower()

    if provider == "ollama":
        model_to_use = cfg.resolve_ollama_model(model)
        selected_base = (base_url or cfg.OLLAMA_BASE_URL).rstrip("/")
        selected_key = cfg.OLLAMA_API_KEY if api_key is None else api_key
        headers = {"Content-Type": "application/json"}
        if selected_key:
            headers["Authorization"] = f"Bearer {selected_key}"
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{selected_base}/{(path or '/api/chat').lstrip('/')}",
                json={
                    "model": model_to_use,
                    "messages": [{"role": "user", "content": prompt}],
                    "format": "json",
                    "stream": False,
                },
                headers=headers,
            )
            resp.raise_for_status()
            return _extract_json_object(resp.json()["message"]["content"])

    if provider == "openai":
        base = (base_url or "https://api.openai.com/v1").rstrip("/")
        if protocol == "openai_responses":
            url = f"{base}/{(path or '/responses').lstrip('/')}"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            payload = {
                "model": model or "gpt-6-astra",
                "input": prompt,
                "instructions": "Return only a valid JSON object.",
            }
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data.get("output_text") or "".join(
                    part.get("text", "")
                    for item in data.get("output", [])
                    for part in item.get("content", [])
                    if part.get("type") == "output_text"
                )
                return _extract_json_object(content)
        url = f"{base}/{(path or '/chat/completions').lstrip('/')}"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model or "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return _extract_json_object(resp.json()["choices"][0]["message"]["content"])

    if provider == "gemini":
        model_name = model or "gemini-1.5-flash"
        gemini_base = (base_url or "https://generativelanguage.googleapis.com").rstrip("/")
        gemini_path = (path or "/v1beta/models/{model}:generateContent").replace(
            "{model}", model_name
        )
        full_url = f"{gemini_base}/{gemini_path.lstrip('/')}?key={api_key or ''}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                full_url, json=payload, headers={"Content-Type": "application/json"}
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return _extract_json_object(text)

    if provider == "anthropic":
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key or "",
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model or "claude-3-5-sonnet-20241022",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{(base_url or 'https://api.anthropic.com/v1').rstrip('/')}/"
                f"{(path or '/messages').lstrip('/')}",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"]
            return _extract_json_object(text)

    raise ValueError(f"Unbekannter LLM-Provider: {provider}")
