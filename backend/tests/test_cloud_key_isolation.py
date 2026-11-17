"""Ein aktives Cloud-Profil spiegelt Adresse und Schlüssel in die Ollama-Felder der Konfiguration. Weder der
Startbildschirm noch Ollama-Rückfälle dürfen diesen Schlüssel an einen Server senden, zu dem er nicht gehört."""

import asyncio

import pytest

from core import config as cfg
from services import chat_start


@pytest.fixture
def cloud_profile_active(monkeypatch):
    monkeypatch.setattr(cfg, "ENV_OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setattr(cfg, "ENV_OLLAMA_API_KEY", "")
    monkeypatch.setattr(cfg, "OLLAMA_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(cfg, "OLLAMA_API_KEY", "sk-cloud-secret")
    monkeypatch.setattr(cfg, "ACTIVE_LLM_PROTOCOL", "openai")
    monkeypatch.setattr(cfg, "ACTIVE_LLM_PROVIDER", "openai")
    monkeypatch.setattr(cfg, "OLLAMA_LLM_MODEL", "gpt-x")


def test_typing_statement_makes_no_request_while_a_cloud_profile_is_active(
    cloud_profile_active, monkeypatch
):
    async def forbidden(*_a, **_k):
        raise AssertionError("cloud request from the start screen")

    monkeypatch.setattr(chat_start, "admitted_post", forbidden)

    statement = asyncio.run(chat_start.generate_typing_statement())

    assert statement in chat_start._FALLBACK_STATEMENTS


def test_ollama_fallback_never_gets_the_cloud_key(cloud_profile_active):
    assert cfg.ollama_fallback_key("http://62.169.158.40:46800") == ""
    assert cfg.ollama_fallback_key("http://ollama:11434") == ""
    assert cfg.ollama_fallback_key("https://api.openai.com/v1") == ""
    assert cfg.default_ollama_base_url() == "http://ollama:11434"


def test_ollama_fallback_keeps_the_key_of_its_own_address(monkeypatch):
    monkeypatch.setattr(cfg, "ENV_OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setattr(cfg, "ENV_OLLAMA_API_KEY", "env-key")
    monkeypatch.setattr(cfg, "OLLAMA_BASE_URL", "https://gpu.intern:11434")
    monkeypatch.setattr(cfg, "OLLAMA_API_KEY", "profile-key")
    monkeypatch.setattr(cfg, "ACTIVE_LLM_PROTOCOL", "ollama")

    assert cfg.ollama_fallback_key("https://gpu.intern:11434/") == "profile-key"
    assert cfg.ollama_fallback_key("http://ollama:11434") == "env-key"
    assert cfg.ollama_fallback_key("http://other:11434") == ""
    assert cfg.default_ollama_base_url() == "https://gpu.intern:11434"
