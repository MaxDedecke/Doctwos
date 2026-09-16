"""Gemeinsame Test-Weichen für die Parser-Tests."""

import os

import pytest


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
