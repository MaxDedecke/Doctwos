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
from api.schemas import (
    AIProfileCreate,
    AIProfileUpdate,
    AISettingsUpdate,
    EmbeddingProfileCreate,
    EmbeddingProfileUpdate,
    ModelUpdateRequest,
)
from core.auth_dependency import get_current_user
from core.inference_admission import InferenceAdmissionTimeout, admitted_post
from core.inference_errors import VllmCapacityError, raise_for_inference_status
from core.teams import require_admin
from core.db_setup import engine, get_db
from models.database import AIProfile, EmbeddingProfile, User
from services.ai_settings import (
    apply_profile,
    apply_runtime_settings,
    ensure_profiles,
    get_settings,
    serialize_profile,
    serialize_embedding_profile,
    ensure_embedding_profiles,
    serialize_settings,
    apply_embedding_profile,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])

_PROFILE_KINDS = {"local", "remote", "cloud"}
_PROFILE_PROTOCOLS = {"ollama", "openai_chat", "openai_responses", "anthropic", "gemini"}


def _joined_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _discovered_model_names(payload: object, provider: str) -> set[str]:
    """Extract model identifiers from Ollama or OpenAI-compatible discovery.

    A successful discovery response alone is not sufficient for a readiness
    check: RunPod may be reachable while the configured model is still pulling
    (or the profile names a model that is not installed on that pod).
    """
    if not isinstance(payload, dict):
        return set()
    entries = payload.get("models") if provider == "ollama" else payload.get("data")
    if not isinstance(entries, list):
        return set()
    key = "name" if provider == "ollama" else "id"
    return {
        item[key].strip()
        for item in entries
        if isinstance(item, dict) and isinstance(item.get(key), str) and item[key].strip()
    }


def _require_discovered_model(response: httpx.Response, model: str, provider: str, label: str) -> None:
    available = _discovered_model_names(response.json(), provider)
    if model not in available:
        logger.warning(
            "profile_readiness_model_mismatch label=%s expected_model=%s available_models=%s",
            label,
            model,
            sorted(available),
        )
        available_hint = ", ".join(sorted(available)) or "keine Modellkennung"
        raise ValueError(
            f"{label}-Modell {model!r} ist am Endpunkt nicht verfügbar "
            f"(gemeldet: {available_hint})."
        )


def _active_discovery_request() -> tuple[str, dict[str, str]]:
    """Return the model-discovery URL and auth for the active profile."""
    path = "/api/tags" if cfg.ACTIVE_LLM_PROTOCOL == "ollama" else "/models"
    headers: dict[str, str] = {}
    if cfg.OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {cfg.OLLAMA_API_KEY}"
    return _joined_url(cfg.OLLAMA_BASE_URL, path), headers


def _validate_profile_values(values: dict, existing: AIProfile | None = None) -> None:
    kind = values.get("kind", existing.kind if existing else None)
    protocol = values.get("protocol", existing.protocol if existing else None)
    if kind not in _PROFILE_KINDS:
        raise HTTPException(status_code=400, detail="kind muss local, remote oder cloud sein")
    if protocol not in _PROFILE_PROTOCOLS:
        raise HTTPException(status_code=400, detail="Unbekanntes LLM-Protokoll")
    provider = values.get("provider", existing.provider if existing else None)
    llm_base_url = values.get("llm_base_url", existing.llm_base_url if existing else None)
    embedding_base_url = values.get(
        "embedding_base_url", existing.embedding_base_url if existing else None
    )
    if kind == "local" and (
        provider != "ollama"
        or protocol != "ollama"
        or llm_base_url != "http://ollama:11434"
        or embedding_base_url != "http://ollama:11434"
    ):
        raise HTTPException(
            status_code=400, detail="Lokale Profile verwenden den internen Ollama-Dienst"
        )
    if kind == "remote" and not llm_base_url:
        raise HTTPException(status_code=400, detail="Remote-Profile benötigen eine URL")
    if kind == "remote" and not embedding_base_url:
        raise HTTPException(status_code=400, detail="Remote-Profile benötigen eine Embedding-URL")
    if protocol == "ollama" and provider != "ollama":
        raise HTTPException(status_code=400, detail="Ollama-Protokoll benötigt den Ollama-Provider")
    if protocol == "openai_chat" and provider not in {"openai", "vllm"}:
        raise HTTPException(
            status_code=400,
            detail="Chat-Completions benötigen OpenAI, vLLM oder einen kompatiblen Provider",
        )
    if protocol == "openai_responses" and provider != "openai":
        raise HTTPException(status_code=400, detail="Responses-Protokoll benötigt den OpenAI-Provider")
    if protocol in {"anthropic", "gemini"} and provider != protocol:
        raise HTTPException(status_code=400, detail="Protokoll und Provider passen nicht zusammen")
    if kind == "remote" and protocol not in {"ollama", "openai_chat"}:
        raise HTTPException(
            status_code=400,
            detail="Remote-Profile unterstützen Ollama oder OpenAI-kompatible APIs",
        )
    if provider == "vllm" and (kind != "remote" or protocol != "openai_chat"):
        raise HTTPException(
            status_code=400,
            detail="vLLM-Profile benötigen Remote und das Chat-Completions-Protokoll",
        )
    if kind == "cloud" and provider not in cfg.CLOUD_LLM_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unbekannter Cloud-Provider")
    embedding_provider = values.get(
        "embedding_provider", existing.embedding_provider if existing else None
    )
    if embedding_provider not in {"ollama", "openai"}:
        raise HTTPException(status_code=400, detail="Unbekannter Embedding-Provider")
    for field in ("llm_path", "embedding_path"):
        value = values.get(field, getattr(existing, field, None) if existing else None)
        if value and not value.startswith("/"):
            raise HTTPException(status_code=400, detail=f"{field} muss mit / beginnen")
    for field in ("embedding_dimension", "embedding_context_length", "llm_context_length"):
        value = values.get(field, getattr(existing, field, None) if existing else None)
        if value is not None and value < 1:
            raise HTTPException(status_code=400, detail=f"{field} muss größer als 0 sein")
    for field in ("name", "provider", "llm_model", "embedding_provider", "embedding_model"):
        value = values.get(field, getattr(existing, field, None) if existing else None)
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(status_code=400, detail=f"{field} darf nicht leer sein")


def _validate_embedding_profile_values(values: dict, existing: EmbeddingProfile | None = None) -> None:
    provider = values.get("provider", existing.provider if existing else None)
    if provider not in {"ollama", "openai"}:
        raise HTTPException(status_code=400, detail="Unbekannter Embedding-Provider")
    for field in ("name", "model", "base_url"):
        value = values.get(field, getattr(existing, field, None) if existing else None)
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(status_code=400, detail=f"{field} darf nicht leer sein")
    path = values.get("path", existing.path if existing else None)
    if not isinstance(path, str) or not path.startswith("/"):
        raise HTTPException(status_code=400, detail="path muss mit / beginnen")
    for field in ("dimension", "context_length"):
        value = values.get(field, getattr(existing, field, None) if existing else None)
        if value is not None and value < 1:
            raise HTTPException(status_code=400, detail=f"{field} muss größer als 0 sein")


@router.get("/")
async def root():
    return {"message": "Doctus AI Backend is running"}


@router.get("/health/live")
async def liveness():
    """Confirm that the API process can serve HTTP requests.

    Container liveness must not depend on remote inference discovery. A model
    provider can be misconfigured or temporarily unavailable while the API is
    still running and able to serve non-LLM routes. Use `/health` for the
    dependency/readiness details.
    """
    return {"status": "alive"}


@router.get("/health")
async def health(response: Response):
    """
    Dependency/readiness check. Unlike `/health/live`, this also checks the
    database, Redis, and the active LLM discovery endpoint. A provider-specific
    404 is reported here without making the API container itself unhealthy.
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
        discovery_url, headers = _active_discovery_request()
        async with httpx.AsyncClient(timeout=3.0) as client:
            if getattr(cfg, "ACTIVE_LLM_PROVIDER", "ollama") == "vllm":
                base = cfg.OLLAMA_BASE_URL.rstrip("/")
                root_url = base[:-3] if base.endswith("/v1") else base
                health_resp = await client.get(_joined_url(root_url, "/health"), headers=headers)
                if health_resp.status_code == 200:
                    resp = await client.get(discovery_url, headers=headers)
                    checks["vllm"] = "ok" if resp.status_code == 200 else f"error: HTTP {resp.status_code}"
                else:
                    checks["vllm"] = f"error: health HTTP {health_resp.status_code}"
            else:
                resp = await client.get(discovery_url, headers=headers)
                checks["ollama"] = (
                    "ok" if resp.status_code == 200 else f"error: HTTP {resp.status_code}"
                )
    except Exception as e:
        key = "vllm" if getattr(cfg, "ACTIVE_LLM_PROVIDER", "ollama") == "vllm" else "ollama"
        checks[key] = f"error: {e}"

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
def read_ai_settings(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    settings = get_settings(db)
    db.commit()
    return serialize_settings(settings)


@router.get("/ai-profiles")
def read_ai_profiles(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    settings = get_settings(db)
    profiles = ensure_profiles(db, settings)
    db.commit()
    return {
        "active_profile_id": settings.active_profile_id,
        "profiles": [
            serialize_profile(profile, active_id=settings.active_profile_id) for profile in profiles
        ],
    }


@router.get("/embedding-profiles")
def list_embedding_profiles(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    settings = get_settings(db)
    profiles = ensure_embedding_profiles(db, settings)
    db.commit()
    return {
        "active_embedding_profile_id": settings.active_embedding_profile_id,
        "profiles": [serialize_embedding_profile(p, active_id=settings.active_embedding_profile_id) for p in profiles],
    }


@router.post("/embedding-profiles", status_code=201)
def create_embedding_profile(
    request: EmbeddingProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    values = request.model_dump()
    _validate_embedding_profile_values(values)
    profile = EmbeddingProfile(**values, created_by_user_id=user.id, is_system=False)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return serialize_embedding_profile(profile)


@router.patch("/embedding-profiles/{profile_id}")
def update_embedding_profile(
    profile_id: int,
    request: EmbeddingProfileUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    profile = db.query(EmbeddingProfile).filter(EmbeddingProfile.id == profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Embedding-Profil nicht gefunden")
    values = request.model_dump(exclude_unset=True)
    _validate_embedding_profile_values(values, profile)
    for field, value in values.items():
        if field == "api_key":
            if value is not None:
                setattr(profile, field, value or None)
        elif value is not None:
            setattr(profile, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(profile)
    settings = get_settings(db)
    if settings.active_embedding_profile_id == profile.id:
        apply_embedding_profile(settings, profile)
        db.commit()
    return serialize_embedding_profile(profile, active_id=settings.active_embedding_profile_id)


@router.delete("/embedding-profiles/{profile_id}", status_code=204)
def delete_embedding_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    profile = db.query(EmbeddingProfile).filter(EmbeddingProfile.id == profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Embedding-Profil nicht gefunden")
    settings = get_settings(db)
    if profile.is_system or settings.active_embedding_profile_id == profile.id:
        raise HTTPException(status_code=409, detail="System- oder aktives Profil kann nicht gelöscht werden")
    db.delete(profile)
    db.commit()


@router.post("/embedding-profiles/{profile_id}/activate")
def activate_embedding_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    profile = db.query(EmbeddingProfile).filter(EmbeddingProfile.id == profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Embedding-Profil nicht gefunden")
    settings = get_settings(db)
    apply_embedding_profile(settings, profile)
    settings.updated_by_user_id = user.id
    db.commit()
    return serialize_embedding_profile(profile, active_id=profile.id)


@router.post("/embedding-profiles/{profile_id}/test")
async def test_embedding_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    profile = db.query(EmbeddingProfile).filter(EmbeddingProfile.id == profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Embedding-Profil nicht gefunden")
    headers = {"Content-Type": "application/json"}
    if profile.api_key:
        headers["Authorization"] = f"Bearer {profile.api_key}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await admitted_post(
                client,
                _joined_url(profile.base_url, profile.path),
                kind="batch",
                wait_timeout_seconds=15.0,
                json={"model": profile.model, "input": "Doctus connection test"},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            if profile.provider == "openai":
                embedding = payload["data"][0]["embedding"]
            else:
                embedding = payload["embeddings"][0]
            if len(embedding) != profile.dimension:
                raise ValueError(
                    f"Endpunkt liefert {len(embedding)} Dimensionen, Profil erwartet {profile.dimension}"
                )
        return {"ok": True, "dimension": len(embedding)}
    except InferenceAdmissionTimeout as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Embedding-Endpunkt fehlgeschlagen: {exc}") from exc


@router.post("/ai-profiles", status_code=201)
def create_ai_profile(
    request: AIProfileCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    values = request.model_dump()
    _validate_profile_values(values)
    profile = AIProfile(**values, created_by_user_id=user.id, is_system=False)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return serialize_profile(profile)


@router.patch("/ai-profiles/{profile_id}")
def update_ai_profile(
    profile_id: int,
    request: AIProfileUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    profile = db.query(AIProfile).filter(AIProfile.id == profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="AI-Profil nicht gefunden")
    values = request.model_dump(exclude_unset=True)
    _validate_profile_values(values, profile)
    for field, value in values.items():
        if field in {"llm_api_key", "embedding_api_key"}:
            if value is not None:
                setattr(profile, field, value or None)
        elif value is not None:
            setattr(profile, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(profile)
    settings = get_settings(db)
    if settings.active_profile_id == profile.id:
        apply_profile(settings, profile)
        db.commit()
    return serialize_profile(profile, active_id=settings.active_profile_id)


@router.delete("/ai-profiles/{profile_id}", status_code=204)
def delete_ai_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    profile = db.query(AIProfile).filter(AIProfile.id == profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="AI-Profil nicht gefunden")
    settings = get_settings(db)
    if profile.is_system or settings.active_profile_id == profile.id:
        raise HTTPException(
            status_code=409, detail="System- oder aktives Profil kann nicht gelöscht werden"
        )
    db.delete(profile)
    db.commit()


@router.post("/ai-profiles/{profile_id}/activate")
def activate_ai_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    profile = db.query(AIProfile).filter(AIProfile.id == profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="AI-Profil nicht gefunden")
    if profile.kind == "cloud" and not cfg.cloud_llm_allowed():
        raise HTTPException(status_code=403, detail="Cloud-LLM-Provider sind deaktiviert")
    settings = get_settings(db)
    apply_profile(settings, profile)
    settings.updated_by_user_id = user.id
    db.commit()
    return serialize_profile(profile, active_id=profile.id)


@router.post("/ai-profiles/{profile_id}/test")
async def test_ai_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_admin),
):
    profile = db.query(AIProfile).filter(AIProfile.id == profile_id).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="AI-Profil nicht gefunden")
    probes: list[tuple[str, str, str | None]] = []
    if profile.provider == "vllm":
        vllm_base = (profile.llm_base_url or "http://vllm:8000/v1").rstrip("/")
        vllm_root = vllm_base[:-3] if vllm_base.endswith("/v1") else vllm_base
        probes.append(("health", _joined_url(vllm_root, "/health"), profile.llm_api_key))
    if profile.protocol == "ollama":
        probes.append(
            (
                "chat",
                _joined_url(profile.llm_base_url or "http://ollama:11434", "/api/tags"),
                profile.llm_api_key,
            )
        )
    elif profile.protocol in {"openai_chat", "openai_responses"}:
        probes.append(
            (
                "chat",
                _joined_url(profile.llm_base_url or "https://api.openai.com/v1", "/models"),
                profile.llm_api_key,
            )
        )
    if profile.embedding_provider in {"ollama", "openai"}:
        discovery_path = "/api/tags" if profile.embedding_provider == "ollama" else "/models"
        probes.append(
            (
                "embedding",
                _joined_url(
                    profile.embedding_base_url or "http://ollama:11434",
                    discovery_path,
                ),
                profile.embedding_api_key,
            )
        )

    results = {"chat": "configuration-valid", "embedding": "configuration-valid"}
    label = "profile"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for label, url, api_key in probes:
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                response = await client.get(url, headers=headers)
                raise_for_inference_status(
                    response,
                    profile.embedding_provider if label == "embedding" else profile.provider,
                )
                if label == "chat":
                    _require_discovered_model(response, profile.llm_model, profile.provider, label)
                elif label == "embedding":
                    _require_discovered_model(
                        response, profile.embedding_model, profile.embedding_provider, label
                    )
                results[label] = "reachable"
            if profile.provider == "vllm":
                label = "tool_calling"
                response = await admitted_post(
                    client,
                    _joined_url(
                        profile.llm_base_url or "http://vllm:8000/v1",
                        profile.llm_path or "/chat/completions",
                    ),
                    kind="chat",
                    wait_timeout_seconds=15.0,
                    json={
                        "model": profile.llm_model,
                        "messages": [{"role": "user", "content": "Call the probe tool now."}],
                        "tools": [{
                            "type": "function",
                            "function": {
                                "name": "doctus_profile_probe",
                                "description": "Connection test. Do not perform external actions.",
                                "parameters": {"type": "object", "properties": {}, "required": []},
                            },
                        }],
                        "tool_choice": "required",
                        "stream": False,
                        "max_tokens": 32,
                    },
                    headers={
                        "Content-Type": "application/json",
                        **({"Authorization": f"Bearer {profile.llm_api_key}"} if profile.llm_api_key else {}),
                    },
                )
                raise_for_inference_status(response, profile.provider)
                payload = response.json()
                choices = payload.get("choices", []) if isinstance(payload, dict) else []
                first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
                message = first_choice.get("message", {})
                tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []
                if not any(
                    isinstance(call.get("function"), dict)
                    and call["function"].get("name") == "doctus_profile_probe"
                    for call in tool_calls if isinstance(call, dict)
                ):
                    raise ValueError(
                        "vLLM hat keinen Tool-Aufruf zurückgegeben. Prüfe --enable-auto-tool-choice, "
                        "--tool-call-parser und das Chat-Template des Modells."
                    )
                results[label] = "supported"
        return {"ok": True, **results}
    except VllmCapacityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InferenceAdmissionTimeout as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        if profile.provider == "vllm":
            try:
                detail = exc.response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                detail = ""
            if any(marker in str(detail).lower() for marker in ("out of memory", "kv cache", "cuda", "gpu memory")):
                raise HTTPException(
                    status_code=503,
                    detail="vLLM ist ausgelastet oder hat nicht genug GPU-/KV-Cache-Speicher. "
                    "Bitte Parallelität, Kontextlänge oder Modellgröße reduzieren.",
                ) from exc
        if profile.provider == "vllm" and label == "tool_calling":
            raise HTTPException(
                status_code=502,
                detail=(
                    "vLLM hat den Tool-Calling-Test abgelehnt. Prüfe vLLM >= 0.8.3, "
                    "--enable-auto-tool-choice, --tool-call-parser und das Chat-Template."
                ),
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"{label.capitalize()}-Endpunkt fehlgeschlagen (HTTP {exc.response.status_code})",
        ) from exc
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"{label.capitalize()}-Endpunkt nicht erreichbar: {exc}",
        ) from exc


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
    """List models exposed by the active Ollama/OpenAI-compatible profile."""
    try:
        discovery_url, headers = _active_discovery_request()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(discovery_url, headers=headers)
            if resp.status_code == 200:
                if cfg.ACTIVE_LLM_PROTOCOL == "ollama":
                    models = [m["name"] for m in resp.json().get("models", [])]
                else:
                    models = [m["id"] for m in resp.json().get("data", [])]
                return {"models": models}
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Ollama-Modelle: {e}")
    return {"models": [cfg.OLLAMA_LLM_MODEL, cfg.OLLAMA_EMBED_MODEL]}
