"""Persistent, deployment-wide AI configuration shared by API and workers."""

from dataclasses import dataclass
from typing import Any

import core.config as cfg
from models.database import AIProfile, AISettings, EmbeddingProfile
from sqlalchemy.orm import Session


@dataclass
class RuntimeAISettings:
    llm_provider: str
    llm_model: str
    llm_base_url: str
    llm_api_key: str
    embedding_provider: str
    embedding_model: str
    embedding_base_url: str
    embedding_api_key: str
    embedding_dimension: int
    embedding_context_length: int
    llm_context_length: int


LOCAL_OLLAMA_URL = "http://ollama:11434"


def ensure_profiles(db: Session, settings: AISettings) -> list[AIProfile]:
    profiles = db.query(AIProfile).order_by(AIProfile.id).all()
    if profiles:
        if settings.active_profile_id is None:
            settings.active_profile_id = profiles[0].id
        return profiles
    local = AIProfile(
        name="Lokales Ollama",
        kind="local",
        provider="ollama",
        protocol="ollama",
        llm_model=settings.llm_model or cfg.OLLAMA_LLM_MODEL,
        llm_base_url=LOCAL_OLLAMA_URL,
        llm_path="/api/chat",
        embedding_provider="ollama",
        embedding_model=settings.embedding_model or cfg.OLLAMA_EMBED_MODEL,
        embedding_base_url=LOCAL_OLLAMA_URL,
        embedding_path="/api/embed",
        embedding_dimension=settings.embedding_dimension,
        embedding_context_length=settings.embedding_context_length,
        llm_context_length=settings.llm_context_length,
        is_system=True,
    )
    db.add(local)
    db.flush()
    settings.active_profile_id = local.id
    return [local]


def ensure_embedding_profiles(db: Session, settings: AISettings) -> list[EmbeddingProfile]:
    profiles = db.query(EmbeddingProfile).order_by(EmbeddingProfile.id).all()
    if profiles:
        if settings.active_embedding_profile_id is None:
            settings.active_embedding_profile_id = profiles[0].id
        return profiles
    profile = EmbeddingProfile(
        name="Standard-Embedding",
        provider=settings.embedding_provider or cfg.EMBEDDING_PROVIDER,
        model=settings.embedding_model or cfg.OLLAMA_EMBED_MODEL,
        base_url=settings.embedding_base_url or cfg.EMBEDDING_BASE_URL,
        path="/embeddings" if (settings.embedding_provider or cfg.EMBEDDING_PROVIDER) == "openai" else "/api/embed",
        api_key=settings.embedding_api_key or None,
        dimension=settings.embedding_dimension,
        context_length=settings.embedding_context_length,
        is_system=True,
    )
    db.add(profile)
    db.flush()
    settings.active_embedding_profile_id = profile.id
    return [profile]


def get_active_profile(db: Session) -> AIProfile:
    settings = get_settings(db)
    profiles = ensure_profiles(db, settings)
    profile = next((item for item in profiles if item.id == settings.active_profile_id), None)
    return profile or profiles[0]


def get_profile(db: Session, profile_id: int | None) -> AIProfile:
    if profile_id is None:
        return get_active_profile(db)
    profile = db.query(AIProfile).filter(AIProfile.id == profile_id).first()
    if profile is None:
        raise LookupError("AI-Profil nicht gefunden")
    return profile


def get_active_embedding_profile(db: Session) -> EmbeddingProfile:
    settings = get_settings(db)
    profiles = ensure_embedding_profiles(db, settings)
    profile = next((item for item in profiles if item.id == settings.active_embedding_profile_id), None)
    return profile or profiles[0]


def serialize_embedding_profile(profile: EmbeddingProfile, *, active_id: int | None = None) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "provider": profile.provider,
        "model": profile.model,
        "base_url": profile.base_url,
        "path": profile.path,
        "api_key_set": bool(profile.api_key),
        "dimension": profile.dimension,
        "context_length": profile.context_length,
        "is_system": profile.is_system,
        "is_active": active_id == profile.id,
    }


def serialize_profile(profile: AIProfile, *, active_id: int | None = None) -> dict[str, Any]:
    return {
        "id": profile.id,
        "name": profile.name,
        "kind": profile.kind,
        "provider": profile.provider,
        "protocol": profile.protocol,
        "llm_model": profile.llm_model,
        "llm_base_url": profile.llm_base_url,
        "llm_path": profile.llm_path,
        "llm_api_key_set": bool(profile.llm_api_key),
        "embedding_provider": profile.embedding_provider,
        "embedding_model": profile.embedding_model,
        "embedding_base_url": profile.embedding_base_url,
        "embedding_path": profile.embedding_path,
        "embedding_api_key_set": bool(profile.embedding_api_key),
        "embedding_dimension": profile.embedding_dimension,
        "embedding_context_length": profile.embedding_context_length,
        "llm_context_length": profile.llm_context_length,
        "is_system": profile.is_system,
        "is_active": active_id == profile.id,
    }


def get_settings(db: Session) -> AISettings:
    settings = db.query(AISettings).order_by(AISettings.id).first()
    if settings is None:
        settings = AISettings(
            llm_provider="ollama",
            llm_model=cfg.OLLAMA_LLM_MODEL,
            llm_base_url=cfg.OLLAMA_BASE_URL,
            llm_api_key=cfg.OLLAMA_API_KEY or None,
            embedding_provider=cfg.EMBEDDING_PROVIDER,
            embedding_model=cfg.OLLAMA_EMBED_MODEL,
            embedding_base_url=cfg.EMBEDDING_BASE_URL,
            embedding_api_key=cfg.EMBEDDING_API_KEY or None,
            embedding_dimension=cfg.EMBEDDING_DIMENSION,
            embedding_context_length=cfg.EMBEDDING_CONTEXT_LENGTH,
            llm_context_length=cfg.OLLAMA_NUM_CTX,
        )
        db.add(settings)
        db.flush()
    return settings


def apply_runtime_settings(settings: AISettings) -> None:
    """Apply persisted values to the current API process immediately."""

    cfg.OLLAMA_LLM_MODEL = settings.llm_model
    cfg.OLLAMA_BASE_URL = (settings.llm_base_url or cfg.OLLAMA_BASE_URL).rstrip("/")
    cfg.OLLAMA_API_KEY = settings.llm_api_key or ""
    cfg.ACTIVE_LLM_PROVIDER = settings.llm_provider.lower()
    cfg.ACTIVE_LLM_PROTOCOL = (
        "ollama" if settings.llm_provider.lower() == "ollama" else "openai_chat"
    )
    cfg.ACTIVE_LLM_PATH = (
        "/api/chat" if cfg.ACTIVE_LLM_PROTOCOL == "ollama" else "/chat/completions"
    )
    cfg.OLLAMA_EMBED_MODEL = settings.embedding_model
    cfg.EMBEDDING_PROVIDER = settings.embedding_provider.lower()
    cfg.EMBEDDING_BASE_URL = (settings.embedding_base_url or cfg.OLLAMA_BASE_URL).rstrip("/")
    cfg.EMBEDDING_API_KEY = settings.embedding_api_key or ""
    cfg.EMBEDDING_DIMENSION = settings.embedding_dimension
    cfg.OLLAMA_NUM_CTX = settings.llm_context_length
    cfg.EMBEDDING_CONTEXT_LENGTH = settings.embedding_context_length


def apply_embedding_profile(settings: AISettings, profile: EmbeddingProfile) -> None:
    """Mirror the independent embedding profile into legacy runtime fields."""
    settings.active_embedding_profile_id = profile.id
    settings.embedding_provider = profile.provider
    settings.embedding_model = profile.model
    settings.embedding_base_url = profile.base_url
    settings.embedding_api_key = profile.api_key
    settings.embedding_dimension = profile.dimension
    settings.embedding_context_length = profile.context_length
    cfg.OLLAMA_EMBED_MODEL = profile.model
    cfg.EMBEDDING_PROVIDER = profile.provider.lower()
    cfg.EMBEDDING_BASE_URL = profile.base_url.rstrip("/")
    cfg.EMBEDDING_API_KEY = profile.api_key or ""
    cfg.EMBEDDING_DIMENSION = profile.dimension
    cfg.EMBEDDING_CONTEXT_LENGTH = profile.context_length


def apply_profile(settings: AISettings, profile: AIProfile) -> None:
    """Apply only LLM fields; embedding selection is independent."""
    settings.active_profile_id = profile.id
    settings.llm_provider = profile.provider
    settings.llm_model = profile.llm_model
    settings.llm_base_url = profile.llm_base_url
    settings.llm_api_key = profile.llm_api_key
    settings.llm_context_length = profile.llm_context_length
    apply_runtime_settings(settings)
    cfg.ACTIVE_LLM_PROTOCOL = profile.protocol
    cfg.ACTIVE_LLM_PATH = profile.llm_path


def initialize_runtime_settings(session_factory) -> None:
    """Load persisted settings after migrations; old deployments seed from env."""

    db = session_factory()
    try:
        settings = get_settings(db)
        profiles = ensure_profiles(db, settings)
        ensure_embedding_profiles(db, settings)
        profile = next(
            (item for item in profiles if item.id == settings.active_profile_id), profiles[0]
        )
        apply_profile(settings, profile)
        embedding_profile = get_active_embedding_profile(db)
        apply_embedding_profile(settings, embedding_profile)
        db.commit()
    except Exception:
        db.rollback()
        # Keep startup compatible with pre-migration test/dev databases.
    finally:
        db.close()


def serialize_settings(settings: AISettings) -> dict[str, Any]:
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "llm_api_key_set": bool(settings.llm_api_key),
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "embedding_base_url": settings.embedding_base_url,
        "embedding_api_key_set": bool(settings.embedding_api_key),
        "embedding_dimension": settings.embedding_dimension,
        "embedding_context_length": settings.embedding_context_length,
        "llm_context_length": settings.llm_context_length,
        "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
        "active_embedding_profile_id": settings.active_embedding_profile_id,
    }
