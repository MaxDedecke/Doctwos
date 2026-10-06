"""Gemeinsame Test-Weichen für die Parser-Tests."""

import os

import pytest


@pytest.fixture(autouse=True)
def configure_test_encryption_key(monkeypatch):
    """Keep persistence tests independent from deployment secrets.

    Connector tests mock embeddings, but persisted chunks are encrypted just
    like production chunks.  A deterministic test-only Fernet key lets those
    tests exercise the DB path without requiring a locally configured LLM or
    secret store.
    """
    monkeypatch.setenv(
        "MASTER_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    )


@pytest.fixture(autouse=True)
def folder_sources_may_live_anywhere_in_tests(monkeypatch):
    """Die Wurzel-Prüfung für Ordnerquellen (``WATCHED_ROOT``) hat eigene Tests; sonst liegen Testordner in tmp_path."""
    import connectors.folder as folder

    monkeypatch.setattr(folder, "WATCHED_ROOT", "/")


@pytest.fixture(scope="module")
def anyio_backend():
    """Parser-Connectoren laufen produktiv in asyncio/Celery.

    Die Testumgebung kann zusätzlich Trio installiert haben. Die Connectoren
    verwenden bewusst asyncio-Primitiven (u. a. create_task und AsyncClient)
    und bieten keinen separaten Trio-Produktionspfad; deshalb soll AnyIO hier
    nicht automatisch eine zweite, irreführende Trio-Matrix erzeugen.
    """
    return "asyncio"


@pytest.fixture(autouse=True)
def disable_model_pull_during_connector_tests(monkeypatch):
    """Connector-Tests mocken Embeddings, daher darf kein Ollama-Pull starten.

    Die CI-Parser-Suite hat absichtlich keinen Ollama-Service. Der echte
    Modell-Pull wird separat in den Ollama-Client-Tests bzw. im Compose-
    Integrationstest geprüft.
    """

    async def _noop(_model):
        return None

    monkeypatch.setattr("connectors.base.ensure_model_pulled", _noop)


def _ollama_reachable() -> bool:
    """Ollama erreichbar? Die Antwort entscheidet über skip, nicht über fail.

    Ein paar Tests hier prüfen den Retrieval-/Embedding-Pfad und brauchen dafür
    einen echten Ollama mit bge-m3. Lokal steht der nach `docker compose up -d`;
    die CI-Jobs haben ihn nicht (weder backend noch parser deklarieren einen
    ollama-Service). Ohne diese Weiche wären die Tests in der CI dauerhaft rot —
    und ein dauerhaft roter Job wird nicht mehr gelesen.
    """
    import httpx

    base = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    try:
        httpx.get(f"{base}/api/tags", timeout=2.0).raise_for_status()
        return True
    except Exception:
        return False


requires_ollama = pytest.mark.skipif(
    not _ollama_reachable(),
    reason="Braucht einen erreichbaren Ollama mit bge-m3 (docker compose up -d).",
)


@pytest.fixture(autouse=True)
def _isolate_from_server_ai_profile(monkeypatch):
    """Tests lesen das aktive Embedding-/LLM-Profil nie aus einer erreichbaren DB.

    ollama_client._load_server_settings() greift sonst auf die DB zu, in der ein
    Entwickler-Setup meist ein Remote-Profil (z. B. RunPod) hinterlegt hat -- die
    Ergebnisse haengen dann vom lokalen Zustand ab. Ohne Profil gilt die Worker-Env
    (OLLAMA_BASE_URL/EMBED_MODEL), wie in der CI.
    """
    import ollama_client

    monkeypatch.setattr(ollama_client, "_load_server_settings", lambda: None)


@pytest.fixture(autouse=True)
def _batch_embeddings_follow_the_single_embedding_mock(monkeypatch):
    """Connector-Tests ersetzen ``connectors.base.get_embedding``; der gebündelte Aufruf folgt diesem Mock."""
    import connectors.base as base

    async def fake_batch(texts, model=None, retries=3):
        return [await base.get_embedding(text, model=model) for text in texts]

    monkeypatch.setattr(base, "get_embeddings_batch", fake_batch)


@pytest.fixture(autouse=True)
def documents_are_processed_one_at_a_time_unless_a_test_says_otherwise(monkeypatch):
    """Ohne diese Festlegung fragt die automatische Wahl der Parallelität ein echtes Ollama ab (is_gpu_accelerated)."""
    from core import config

    monkeypatch.setattr(config, "DOC_CONCURRENCY", 1)
