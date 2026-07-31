import httpx
import json
import logging
import os
import re
import asyncio
from typing import Dict, Optional

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

# Keep track of active clients per event loop to ensure thread-safety and loop-safety
_loop_clients: Dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}

def _get_client() -> httpx.AsyncClient:
    """
    Returns a shared httpx.AsyncClient for the currently running event loop.
    Cleans up clients associated with closed loops.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Fallback if no event loop is running (not expected in async tasks)
        return httpx.AsyncClient(timeout=60.0)
    
    # Prune closed event loops from the cache
    closed_loops = [lp for lp in _loop_clients if lp.is_closed()]
    for lp in closed_loops:
        del _loop_clients[lp]
        
    if loop not in _loop_clients:
        _loop_clients[loop] = httpx.AsyncClient(timeout=60.0)
        
    return _loop_clients[loop]

async def get_embedding(text: str, model: str = "bge-m3"):
    """
    Calls the local Ollama API to get embeddings for a given text chunk.
    Reuses a persistent connection pool per event loop.
    """
    # Prepend search_document: prefix if using nomic-embed-text as recommended by Nomic
    if model.startswith("nomic-embed-text"):
        if not text.startswith("search_document:") and not text.startswith("search_query:"):
            text = f"search_document: {text}"

    client = _get_client()
    response = await client.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": model, "prompt": text}
    )
    response.raise_for_status()
    return response.json()["embedding"]

async def get_embeddings_batch(texts: list[str], model: str = "bge-m3", retries=3) -> list[list[float]]:
    """Batched embeddings — ein Request für mehrere Texte mit Exponential Backoff Retry."""
    if not texts:
        return []

    if model.startswith("nomic-embed-text"):
        processed_texts = [
            f"search_document: {t}" if not (t.startswith("search_document:") or t.startswith("search_query:")) else t
            for t in texts
        ]
    else:
        processed_texts = texts
    
    client = _get_client()
    
    for attempt in range(retries):
        try:
            # Ollama /api/embed endpoint (ab v0.1.26) akzeptiert input-Array
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": model, "input": processed_texts},
                timeout=120.0  # Batch braucht mehr Zeit
            )
            response.raise_for_status()
            return response.json()["embeddings"]
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as e:
            if attempt == retries - 1:
                logger.error(f"Ollama final failure after {retries} attempts: {e}")
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(f"Ollama retry {attempt+1}/{retries} nach {wait}s: {e}")
            await asyncio.sleep(wait)
    
    return []

_JSON_FENCE_OPEN_RE = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)


def _parse_json_content(content: str):
    """Reasoning models (e.g. Magistral with think:false) can wrap JSON output
    in a ```json ... ``` fence AND append free-text explanation after it
    despite format="json" (e.g. a trailing "Erläuterung: ..." paragraph) — a
    plain fence-strip-then-json.loads breaks with "Extra data" on that
    trailing prose. raw_decode parses only the first JSON value and ignores
    anything after it, so it's robust to both the fence and the trailing
    text. A no-op for plain content."""
    content = content.strip()
    content = _JSON_FENCE_OPEN_RE.sub("", content, count=1)
    start = content.find("{")
    if start > 0:
        content = content[start:]
    obj, _ = json.JSONDecoder().raw_decode(content)
    return obj


async def get_chat_json(prompt: str, model: str, timeout: float = 60.0, think: Optional[bool] = None):
    """
    Single-shot LLM call via Ollama's native /api/chat with format="json" —
    reliable structured output even for small local models (e.g. mistral-nemo).
    Raises on HTTP or JSON-parse errors; callers decide the fallback behavior.

    think: only set for reasoning models (e.g. Magistral) where the default
    chain-of-thought trace makes calls slow enough to matter — undocumented
    Ollama request field for Magistral specifically, but confirmed working
    (Ollama 0.31.2). Omitted (None) by default so it never affects models
    that don't support it.
    """
    if not model or model == "disabled":
        raise RuntimeError(
            "Lokales Ollama-LLM ist für dieses Deployment deaktiviert; "
            "LLM_MODEL auf einem ausreichend dimensionierten Host konfigurieren."
        )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
    }
    if think is not None:
        payload["think"] = think
    client = _get_client()
    response = await client.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    content = response.json()["message"]["content"]
    return _parse_json_content(content)


async def ensure_model_pulled(model: str):
    """
    Ensures that the required embedding model is available in Ollama.
    Reuses a persistent connection pool per event loop.
    """
    client = _get_client()
    await client.post(
        f"{OLLAMA_BASE_URL}/api/pull",
        json={"name": model},
        timeout=300.0
    )
