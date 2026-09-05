import httpx
import json
import logging
import os
import re
import asyncio
from typing import Dict, Optional

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")

# E-8: get_embeddings_batch() schickte bisher alle Chunks eines Dokuments in
# einem einzigen Request. Ein Lasttest mit synthetischem COBOL-Korpus zeigte:
# bei CPU-only bge-m3 (~1,1 Chunks/s) lief ein Batch von 300 Chunks in allen
# drei Versuchen in den fest verdrahteten 120s-Timeout, waehrend 20 Chunks in
# 18,34s zuverlaessig durchliefen. Ohne GPU haengt ein Sync grosser Dateien
# sonst in Timeout-Retry-Schleifen statt nur langsamer zu sein. Beide Werte
# sind env-steuerbar, damit sie sich an gemessene Kundenhardware anpassen
# lassen, ohne Code zu aendern (docs/ENTSCHEIDUNGEN.md E-8).
EMBED_BATCH_MAX_CHUNKS = int(os.getenv("EMBED_BATCH_MAX_CHUNKS", "20"))
EMBED_BATCH_TIMEOUT = float(os.getenv("EMBED_BATCH_TIMEOUT", "120"))

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
    """Batched embeddings — mehrere Requests à max. EMBED_BATCH_MAX_CHUNKS Texte
    mit Exponential Backoff Retry je Sub-Batch (E-8: verhindert, dass ein
    grosses Dokument in einem einzigen ueberlangen Request in den Timeout laeuft)."""
    if not texts:
        return []

    if model.startswith("nomic-embed-text"):
        processed_texts = [
            f"search_document: {t}" if not (t.startswith("search_document:") or t.startswith("search_query:")) else t
            for t in texts
        ]
    else:
        processed_texts = texts

    embeddings: list[list[float]] = []
    for i in range(0, len(processed_texts), EMBED_BATCH_MAX_CHUNKS):
        sub_batch = processed_texts[i:i + EMBED_BATCH_MAX_CHUNKS]
        embeddings.extend(await _get_embeddings_sub_batch(sub_batch, model, retries))
    return embeddings


async def _get_embeddings_sub_batch(texts: list[str], model: str, retries: int) -> list[list[float]]:
    client = _get_client()

    for attempt in range(retries):
        try:
            # Ollama /api/embed endpoint (ab v0.1.26) akzeptiert input-Array
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/embed",
                json={"model": model, "input": texts},
                timeout=EMBED_BATCH_TIMEOUT  # Batch braucht mehr Zeit
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


async def is_gpu_accelerated(model: str) -> bool:
    """
    O-071: ermittelt, ob `model` in Ollama gerade (teil-)GPU-beschleunigt
    läuft, über Ollamas Laufzeit-Status `/api/ps` (Feld `size_vram` —
    `0` heißt CPU-only, `>0` heißt (teil-)GPU-beschleunigt). Robuster als
    eine reine Host-GPU-Prüfung bei der Installation
    (scripts/lib/env-bootstrap.sh::gpu_ready_for_docker), weil es auch
    erkennt, wenn GPU-Passthrough konfiguriert ist, das Modell aber z. B.
    zu groß fürs VRAM ist und Ollama trotzdem auf CPU zurückfällt.

    `/api/ps` liefert nur für bereits geladene Modelle eine size_vram-
    Angabe; ein winziger Embed-Aufruf lädt `model` bei Bedarf zuerst
    (billig, läuft nur einmal pro Sync-Start). Konservativer Fallback
    (CPU-only annehmen) falls Ollama nicht antwortet oder das Feld fehlt.
    """
    try:
        client = _get_client()
        await client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": model, "input": "warmup"},
            timeout=EMBED_BATCH_TIMEOUT,
        )
        response = await client.get(f"{OLLAMA_BASE_URL}/api/ps", timeout=10.0)
        response.raise_for_status()
        for entry in response.json().get("models", []):
            if entry.get("model") == model or entry.get("name") == model:
                return entry.get("size_vram", 0) > 0
    except (httpx.HTTPError, httpx.RequestError, ValueError, KeyError, TypeError) as e:
        logger.warning(f"is_gpu_accelerated: Ollama-Status nicht auswertbar, nehme CPU-only an: {e}")
    return False


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
