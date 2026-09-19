import httpx
import json
import logging
import os
import re
import asyncio
from typing import Dict, Optional

from db import SessionLocal
from core.inference_admission import admitted_post
from models.database import AIProfile, AISettings, EmbeddingProfile

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

# A managed inference endpoint can expose embeddings independently from chat.
# ``ollama`` uses its native /api/embed format; ``openai`` uses /embeddings.
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", OLLAMA_BASE_URL).rstrip("/")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", OLLAMA_API_KEY)
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").lower()
EMBEDDING_AUTO_PULL = os.getenv("EMBEDDING_AUTO_PULL", "true").lower() in {"1", "true", "yes"}
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

# O-168: ohne explizites num_ctx faellt Ollama auf sein kleines eingebautes
# Default-Kontextfenster zurueck und kuerzt bei Ueberlauf stillschweigend von
# vorne -- fuer den Compliance-Checker hiesse das, dass Regelwerk oder
# Elementinhalt unbemerkt aus dem Prompt fallen koennen. Gleicher Default wie
# backend/core/config.py::OLLAMA_NUM_CTX, hier aber als eigene Env-Variable
# gelesen, weil dieses Modul (anders als backend/agent.py) nicht von
# core.config importiert.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
# O-251: do not derive the embedding limit from the chat context. The Qwen
# embedding deployment is configured for 8100 tokens.
EMBEDDING_CONTEXT_LENGTH = int(os.getenv("EMBEDDING_CONTEXT_LENGTH", "8100"))

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


def _load_server_settings() -> Optional[dict]:
    """Read the admin-configured profile from the shared DB.

    The parser is a separate container, so process-local backend state would
    never reach it. Missing tables/DB connectivity intentionally fall back to
    the worker environment, preserving compatibility during migrations and in
    isolated unit tests.
    """
    try:
        db = SessionLocal()
        try:
            settings = db.query(AISettings).order_by(AISettings.id).first()
            if settings is None:
                return None
            profile = None
            if settings.active_profile_id is not None:
                profile = (
                    db.query(AIProfile).filter(AIProfile.id == settings.active_profile_id).first()
                )
            embedding_profile = None
            if settings.active_embedding_profile_id is not None:
                embedding_profile = (
                    db.query(EmbeddingProfile)
                    .filter(EmbeddingProfile.id == settings.active_embedding_profile_id)
                    .first()
                )
            if profile is not None:
                return {
                    "llm_model": profile.llm_model,
                    "llm_base_url": profile.llm_base_url,
                    "llm_api_key": profile.llm_api_key,
                    "protocol": profile.protocol,
                    "llm_path": profile.llm_path,
                    "embedding_provider": embedding_profile.provider
                    if embedding_profile
                    else profile.embedding_provider,
                    "embedding_model": embedding_profile.model
                    if embedding_profile
                    else profile.embedding_model,
                    "embedding_base_url": embedding_profile.base_url
                    if embedding_profile
                    else profile.embedding_base_url,
                    "embedding_api_key": embedding_profile.api_key
                    if embedding_profile
                    else profile.embedding_api_key,
                    "embedding_path": embedding_profile.path
                    if embedding_profile
                    else profile.embedding_path,
                    "embedding_dimension": embedding_profile.dimension
                    if embedding_profile
                    else profile.embedding_dimension,
                    "embedding_context_length": embedding_profile.context_length
                    if embedding_profile
                    else profile.embedding_context_length,
                    "llm_context_length": profile.llm_context_length,
                }
            return {
                "llm_model": settings.llm_model,
                "llm_base_url": settings.llm_base_url,
                "llm_api_key": settings.llm_api_key,
                "protocol": "ollama" if settings.llm_provider == "ollama" else "openai_chat",
                "llm_path": None,
                "embedding_provider": embedding_profile.provider
                if embedding_profile
                else settings.embedding_provider,
                "embedding_model": embedding_profile.model
                if embedding_profile
                else settings.embedding_model,
                "embedding_base_url": embedding_profile.base_url
                if embedding_profile
                else settings.embedding_base_url,
                "embedding_api_key": embedding_profile.api_key
                if embedding_profile
                else settings.embedding_api_key,
                "embedding_path": None,
                "embedding_dimension": embedding_profile.dimension
                if embedding_profile
                else settings.embedding_dimension,
                "embedding_context_length": embedding_profile.context_length
                if embedding_profile
                else settings.embedding_context_length,
                "llm_context_length": settings.llm_context_length,
            }
        finally:
            db.close()
    except Exception as exc:
        logger.debug("AI settings DB lookup unavailable; using worker env: %s", exc)
        return None


def _effective_embedding_settings(model: Optional[str] = None) -> dict:
    settings = _load_server_settings()
    configured_model = os.getenv("EMBED_MODEL", "bge-m3")
    use_server_model = settings and (model is None or model == configured_model)
    return {
        "provider": settings["embedding_provider"] if settings else EMBEDDING_PROVIDER,
        "base_url": (settings["embedding_base_url"] or OLLAMA_BASE_URL).rstrip("/")
        if settings and settings["embedding_base_url"]
        else EMBEDDING_BASE_URL,
        "api_key": settings["embedding_api_key"] if settings else EMBEDDING_API_KEY,
        "path": settings.get("embedding_path") if settings else None,
        "model": settings["embedding_model"] if use_server_model else (model or configured_model),
        "dimension": settings["embedding_dimension"] if settings else EMBEDDING_DIMENSION,
        "context": settings["embedding_context_length"] if settings else EMBEDDING_CONTEXT_LENGTH,
    }


def get_embedding_input_budget(model: Optional[str] = None) -> int:
    """Input byte bound used by the active embedding profile's validation."""
    return int(_effective_embedding_settings(model)["context"])


def _effective_llm_settings(model: str) -> dict:
    settings = _load_server_settings()
    configured_model = os.getenv("LLM_MODEL", "disabled")
    use_server_model = settings and model in (configured_model, "disabled")
    return {
        "base_url": settings["llm_base_url"].rstrip("/")
        if use_server_model and settings and settings["llm_base_url"]
        else OLLAMA_BASE_URL,
        "api_key": settings["llm_api_key"] if use_server_model and settings else OLLAMA_API_KEY,
        "model": settings["llm_model"] if use_server_model and settings else model,
        "context": settings["llm_context_length"]
        if use_server_model and settings
        else OLLAMA_NUM_CTX,
        "protocol": settings.get("protocol", "ollama")
        if use_server_model and settings
        else "ollama",
        "path": settings.get("llm_path") if use_server_model and settings else None,
    }


def _headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _embedding_url(path: str) -> str:
    return f"{EMBEDDING_BASE_URL}{path}"


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


async def get_embedding(text: str, model: Optional[str] = None):
    """Return one document embedding through the configured provider adapter."""
    return (await get_embeddings_batch([text], model=model))[0]


async def get_embeddings_batch(
    texts: list[str], model: Optional[str] = None, retries=3
) -> list[list[float]]:
    """Batched embeddings — mehrere Requests à max. EMBED_BATCH_MAX_CHUNKS Texte
    mit Exponential Backoff Retry je Sub-Batch (E-8: verhindert, dass ein
    grosses Dokument in einem einzigen ueberlangen Request in den Timeout laeuft)."""
    if not texts:
        return []

    effective = _effective_embedding_settings(model)
    model = effective["model"]
    if model.startswith("nomic-embed-text"):
        processed_texts = [
            f"search_document: {t}"
            if not (t.startswith("search_document:") or t.startswith("search_query:"))
            else t
            for t in texts
        ]
    else:
        processed_texts = texts

    _ensure_embedding_inputs_fit(processed_texts, effective["context"])

    embeddings: list[list[float]] = []
    for i in range(0, len(processed_texts), EMBED_BATCH_MAX_CHUNKS):
        sub_batch = processed_texts[i : i + EMBED_BATCH_MAX_CHUNKS]
        embeddings.extend(await _get_embeddings_sub_batch(sub_batch, model, retries, effective))
    return embeddings


async def _get_embeddings_sub_batch(
    texts: list[str], model: str, retries: int, settings: Optional[dict] = None
) -> list[list[float]]:
    settings = settings or _effective_embedding_settings(model)
    client = _get_client()

    for attempt in range(retries):
        try:
            if settings["provider"] == "openai":
                response = await admitted_post(
                    client,
                    f"{settings['base_url']}/{(settings.get('path') or '/embeddings').lstrip('/')}",
                    kind="batch",
                    json={"model": model, "input": texts},
                    headers=_headers(settings["api_key"]),
                    timeout=EMBED_BATCH_TIMEOUT,
                )
                response.raise_for_status()
                embeddings = [item["embedding"] for item in response.json()["data"]]
                return _validate_embedding_response(
                    embeddings, expected_count=len(texts), expected_dimension=settings["dimension"]
                )

            if settings["provider"] != "ollama":
                raise ValueError(
                    "EMBEDDING_PROVIDER muss 'ollama' oder 'openai' sein, "
                    f"nicht {EMBEDDING_PROVIDER!r}."
                )

            # Ollama /api/embed endpoint (ab v0.1.26) akzeptiert input-Array.
            response = await admitted_post(
                client,
                f"{settings['base_url']}/{(settings.get('path') or '/api/embed').lstrip('/')}",
                kind="batch",
                json={
                    "model": model,
                    "input": texts,
                    "dimensions": settings["dimension"],
                    "options": {"num_ctx": settings["context"]},
                },
                headers=_headers(settings["api_key"]),
                timeout=EMBED_BATCH_TIMEOUT,  # Batch braucht mehr Zeit
            )
            response.raise_for_status()
            return _validate_embedding_response(
                response.json()["embeddings"],
                expected_count=len(texts),
                expected_dimension=settings["dimension"],
            )
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as e:
            if attempt == retries - 1:
                logger.error(f"Ollama final failure after {retries} attempts: {e}")
                raise
            wait = 2**attempt  # 1s, 2s, 4s
            logger.warning(f"Ollama retry {attempt + 1}/{retries} nach {wait}s: {e}")
            await asyncio.sleep(wait)

    return []


def _validate_embedding_response(
    embeddings: object, *, expected_count: int, expected_dimension: int
) -> list[list[float]]:
    """Reject incomplete or mixed vector spaces before persistence."""
    if not isinstance(embeddings, list) or len(embeddings) != expected_count:
        raise ValueError(
            "Embedding-Endpunkt lieferte eine falsche Anzahl Vektoren: "
            f"erwartet {expected_count}, erhalten "
            f"{len(embeddings) if isinstance(embeddings, list) else type(embeddings).__name__}."
        )
    for index, embedding in enumerate(embeddings):
        if not isinstance(embedding, list) or len(embedding) != expected_dimension:
            actual = len(embedding) if isinstance(embedding, list) else type(embedding).__name__
            raise ValueError(
                "Embedding-Endpunkt lieferte eine falsche Dimension für Vektor "
                f"{index}: erwartet {expected_dimension}, erhalten {actual}."
            )
    return embeddings


def _ensure_embedding_inputs_fit(texts: list[str], context_length: int) -> None:
    """Reject inputs whose UTF-8 byte upper bound exceeds the token budget.

    Qwen's tokenizer is not bundled with the worker, so pretending that a
    character count equals tokens would be incorrect. UTF-8 bytes are a
    conservative upper bound for byte-pair tokenizers: an input that fits the
    bound cannot be silently truncated by exceeding the configured context.
    Normal source chunks (1000 characters) remain well below this limit.
    """
    for index, text in enumerate(texts):
        upper_bound = len(text.encode("utf-8"))
        if upper_bound > context_length:
            raise ValueError(
                "Embedding-Eingabe überschreitet das konfigurierte Tokenbudget: "
                f"Element {index} benötigt höchstens {upper_bound} UTF-8-Bytes, "
                f"erlaubt sind {context_length}."
            )


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


async def get_chat_json(
    prompt: str, model: str, timeout: float = 60.0, think: Optional[bool] = None
):
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

    settings = _effective_llm_settings(model)
    if settings["protocol"] in {"openai_chat", "openai_responses"}:
        if settings["protocol"] == "openai_responses":
            payload = {
                "model": settings["model"],
                "input": prompt,
                "instructions": "Return only a valid JSON object.",
            }
            default_path = "/responses"
        else:
            payload = {
                "model": settings["model"],
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            }
            default_path = "/chat/completions"
        client = _get_client()
        response = await admitted_post(
            client,
            f"{settings['base_url']}/{(settings.get('path') or default_path).lstrip('/')}",
            kind="batch",
            json=payload,
            headers=_headers(settings["api_key"]),
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        if settings["protocol"] == "openai_responses":
            content = data.get("output_text") or "".join(
                part.get("text", "")
                for item in data.get("output", [])
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
        else:
            content = data["choices"][0]["message"]["content"]
        return _parse_json_content(content)
    payload = {
        "model": settings["model"],
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False,
        "options": {"num_ctx": settings["context"]},
    }
    if think is not None:
        payload["think"] = think
    client = _get_client()
    response = await admitted_post(
        client,
        f"{settings['base_url']}/{(settings.get('path') or '/api/chat').lstrip('/')}",
        kind="batch",
        json=payload,
        headers=_headers(settings["api_key"]),
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
    settings = _effective_embedding_settings(model)
    configured_model = os.getenv("EMBED_MODEL", "bge-m3")
    model = settings["model"] if model == configured_model else model
    if settings["provider"] != "ollama":
        return False

    try:
        client = _get_client()
        await admitted_post(
            client,
            f"{settings['base_url']}/{(settings.get('path') or '/api/embed').lstrip('/')}",
            kind="batch",
            json={
                "model": model,
                "input": "warmup",
                "dimensions": settings["dimension"],
                "options": {"num_ctx": settings["context"]},
            },
            headers=_headers(settings["api_key"]),
            timeout=EMBED_BATCH_TIMEOUT,
        )
        response = await client.get(f"{settings['base_url']}/api/ps", timeout=10.0)
        response.raise_for_status()
        for entry in response.json().get("models", []):
            if entry.get("model") == model or entry.get("name") == model:
                return entry.get("size_vram", 0) > 0
    except (httpx.HTTPError, httpx.RequestError, ValueError, KeyError, TypeError) as e:
        logger.warning(
            f"is_gpu_accelerated: Ollama-Status nicht auswertbar, nehme CPU-only an: {e}"
        )
    return False


async def ensure_model_pulled(model: str):
    """
    Ensures that the required embedding model is available in Ollama.
    Reuses a persistent connection pool per event loop.
    """
    settings = _effective_embedding_settings(model)
    configured_model = os.getenv("EMBED_MODEL", "bge-m3")
    model = settings["model"] if model == configured_model else model
    if not EMBEDDING_AUTO_PULL:
        return
    if settings["provider"] != "ollama":
        return
    client = _get_client()
    await client.post(
        f"{settings['base_url']}/api/pull",
        json={"name": model},
        headers=_headers(settings["api_key"]),
        timeout=300.0,
    )
