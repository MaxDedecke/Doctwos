"""Persistent, deployment-wide AI configuration shared by API and workers."""

from dataclasses import dataclass
from typing import Any

import core.config as cfg
from models.database import AISettings
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
    cfg.OLLAMA_EMBED_MODEL = settings.embedding_model
    cfg.EMBEDDING_PROVIDER = settings.embedding_provider.lower()
    cfg.EMBEDDING_BASE_URL = (
        settings.embedding_base_url or cfg.OLLAMA_BASE_URL
    ).rstrip("/")
    cfg.EMBEDDING_API_KEY = settings.embedding_api_key or ""
    cfg.EMBEDDING_DIMENSION = settings.embedding_dimension
    cfg.OLLAMA_NUM_CTX = settings.llm_context_length
    cfg.EMBEDDING_CONTEXT_LENGTH = settings.embedding_context_length


def initialize_runtime_settings(session_factory) -> None:
    """Load persisted settings after migrations; old deployments seed from env."""

    db = session_factory()
    try:
        settings = get_settings(db)
        db.commit()
        apply_runtime_settings(settings)
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
    }
