"""Gemeinsame Test-Weichen für die Parser-Tests."""

import os

import pytest


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
