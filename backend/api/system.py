"""
backend/api/system.py
======================
System-Endpoints: Health-Check, LLM-Modell-Verwaltung, Ollama-Modell-Liste.

Besonderheit: POST /model-info mutiert cfg.OLLAMA_LLM_MODEL zur Laufzeit.
    Diese Mutation gilt nur für den laufenden Prozess (bis zum nächsten Container-Neustart).
    Alle anderen Router, die cfg.OLLAMA_LLM_MODEL lesen, sehen den neuen Wert sofort,
    da Python Module-Objekte als Singletons funktionieren — aber nur wenn sie
    mit "import core.config as cfg" und nicht "from core.config import OLLAMA_LLM_MODEL"
    importieren (letzteres würde einen lokalen Kopie-Wert erzeugen der nicht aktualisiert wird).
"""

import logging
import os

import httpx
import redis
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text

import core.config as cfg
from api.schemas import AISettingsUpdate, ModelUpdateRequest
from core.auth_dependency import get_current_user
from core.teams import require_admin
from core.db_setup import engine, get_db
from models.database import User
from services.ai_settings import apply_runtime_settings, get_settings, serialize_settings
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/")
async def root():
    return {"message": "Doctus AI Backend is running"}


@router.get("/health")
async def health(response: Response):
    """
    Readiness check — pings every dependency the app actually needs to serve
    traffic, instead of the previous hardcoded {"status": "healthy"} which
    couldn't tell an "Up" container from one wedged against a dead DB/Redis/
    Ollama connection (docker-compose.yml has no healthcheck: block either;
    see docs/DEPLOYMENT.md, "Monitoring").
    """
    checks = {}

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    try:
        r = redis.from_url(cfg.REDIS_URL, socket_connect_timeout=3)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{cfg.OLLAMA_BASE_URL}/api/tags")
            checks["ollama"] = (
                "ok" if resp.status_code == 200 else f"error: HTTP {resp.status_code}"
            )
    except Exception as e:
        checks["ollama"] = f"error: {e}"

    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = 503
    return {"status": "healthy" if healthy else "degraded", "checks": checks}


@router.get("/version")
async def version():
    """
    Reports what's actually running, independent of the diagnostics bundle
    (see docs/DEPLOYMENT.md, "Diagnostics bundle") — GIT_SHA/BUILD_TIME are baked in
    at image build time (see backend/Dockerfile), not read from a .git dir
    that doesn't exist in the deployed container.
    """
    return {
        "git_sha": os.environ.get("GIT_SHA", "unknown"),
        "build_time": os.environ.get("BUILD_TIME", "unknown"),
    }


@router.get("/model-info")
async def model_info():
    return {"llm": cfg.OLLAMA_LLM_MODEL, "embedding": cfg.OLLAMA_EMBED_MODEL}


@router.post("/model-info")
async def update_model_info(
    request: ModelUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    settings = get_settings(db)
    settings.llm_model = request.llm
    db.commit()
    db.refresh(settings)
    apply_runtime_settings(settings)
    return {"llm": settings.llm_model, "embedding": settings.embedding_model}


@router.get("/ai-settings")
def read_ai_settings(
    db: Session = Depends(get_db), _user: User = Depends(get_current_user)
):
    settings = get_settings(db)
    db.commit()
    return serialize_settings(settings)


@router.patch("/ai-settings")
def update_ai_settings(
    request: AISettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    values = request.model_dump(exclude_unset=True)
    for field in (
        "llm_provider",
        "llm_model",
        "llm_base_url",
        "embedding_provider",
        "embedding_model",
        "embedding_base_url",
    ):
        if field in values and values[field] is not None:
            values[field] = values[field].strip()
            if not values[field]:
                raise HTTPException(status_code=400, detail=f"{field} darf nicht leer sein")

    for field in ("embedding_dimension", "embedding_context_length", "llm_context_length"):
        if field in values and (values[field] is None or values[field] < 1):
            raise HTTPException(status_code=400, detail=f"{field} muss größer als 0 sein")

    settings = get_settings(db)
    for field, value in values.items():
        if field in {"llm_api_key", "embedding_api_key"}:
            # An empty value explicitly clears a key; omitted values preserve it.
            setattr(settings, field, value or None)
        elif value is not None:
            setattr(settings, field, value)
    settings.updated_by_user_id = user.id
    db.commit()
    db.refresh(settings)
    apply_runtime_settings(settings)
    return serialize_settings(settings)


@router.get("/models")
async def get_models():
    """Gibt die installierten Ollama-Modelle zurück. Fallback: konfigurietes LLM + Embedding-Modell."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{cfg.OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                return {"models": models}
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Ollama-Modelle: {e}")
    return {"models": [cfg.OLLAMA_LLM_MODEL, cfg.OLLAMA_EMBED_MODEL]}
