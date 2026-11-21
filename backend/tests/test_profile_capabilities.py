"""Geprüfte Fähigkeiten je KI-Profil: Prüflauf über die Chat-Adapter, Veralten, Wirkung auf den Agenten."""

import contextlib
import json
from types import SimpleNamespace

import httpx
import pytest

from doctus_models.database import AIProfile
from services import profile_capabilities
from services.profile_capabilities import (
    probe_capabilities,
    requests_reasoning_summary,
    stored_capabilities,
    supports_tools,
)


def _profile(**overrides) -> SimpleNamespace:
    values = dict(
        id=7,
        provider="ollama",
        protocol="ollama",
        llm_model="qwen3:8b",
        llm_base_url="http://ollama:11434",
        llm_path="/api/chat",
        llm_api_key=None,
        llm_context_length=8192,
        capabilities_json=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _checked(**capabilities) -> dict:
    return {
        "model": "qwen3:8b",
        "protocol": "ollama",
        "base_url": "http://ollama:11434",
        **capabilities,
    }


def test_a_negative_check_switches_the_agent_off_only_for_the_checked_model():
    assert supports_tools(_profile()) is True
    assert supports_tools(_profile(capabilities_json=_checked(tools=False))) is False
    # Anderes Modell im selben Profil: das alte Ergebnis ist veraltet, das Profil wieder ungeprüft.
    stale = _profile(llm_model="qwen3:32b", capabilities_json=_checked(tools=False))
    assert stored_capabilities(stale) is None and supports_tools(stale) is True
    assert supports_tools(_profile(protocol="unbekannt")) is False


def test_reasoning_summaries_are_requested_only_after_a_positive_check():
    profile = _profile(protocol="openai_responses", llm_base_url=None)
    assert requests_reasoning_summary(profile) is False
    profile.capabilities_json = {
        "model": "qwen3:8b",
        "protocol": "openai_responses",
        "base_url": None,
        "reasoning_summary": True,
    }
    assert requests_reasoning_summary(profile) is True


def _serve_ollama(monkeypatch, turns: list[list[dict]]) -> list[dict]:
    requests = []

    @contextlib.asynccontextmanager
    async def mock_stream(_client, url, **kwargs):
        requests.append(json.loads(json.dumps(kwargs["json"])))
        chunks = turns[len(requests) - 1]

        async def lines():
            for chunk in chunks:
                yield json.dumps(chunk)

        yield SimpleNamespace(is_success=True, aiter_lines=lines)

    monkeypatch.setattr("services.agent_providers.admitted_stream", mock_stream)
    return requests


def _call(arguments: dict) -> list[dict]:
    call = {"id": "c1", "function": {"name": "doctus_probe", "arguments": arguments}}
    return [{"message": {"content": "", "tool_calls": [call]}, "done": True}]


@pytest.mark.asyncio
async def test_the_check_runs_a_tool_round_trip_through_the_chat_adapter(monkeypatch):
    requests = _serve_ollama(
        monkeypatch,
        [
            _call({"word": "Doctus"}),
            [
                {"message": {"thinking": "Kennwort suchen", "content": ""}, "done": False},
                {"message": {"content": "KIWI-"}, "done": False},
                {"message": {"content": "4711"}, "done": True},
            ],
        ],
    )

    result = await probe_capabilities(_profile())

    assert result["tools"] and result["tool_arguments"] and result["tool_roundtrip"]
    assert result["streaming"] is True and result["reasoning"] is True
    assert result["error"] is None and result["model"] == "qwen3:8b"
    assert requests[0]["tools"][0]["function"]["name"] == "doctus_probe"
    assert "tools" not in requests[1]  # zweiter Zug ohne Werkzeuge (tool_choice "none")


@pytest.mark.asyncio
async def test_a_model_that_answers_instead_of_calling_the_tool_fails_the_check(monkeypatch):
    _serve_ollama(monkeypatch, [[{"message": {"content": "Gern!"}, "done": True}]])

    result = await probe_capabilities(_profile())

    assert result["tools"] is False and result["tool_roundtrip"] is False
    assert supports_tools(_profile(capabilities_json=result)) is False


@pytest.mark.asyncio
async def test_an_unreachable_server_leaves_the_capabilities_open(monkeypatch):
    @contextlib.asynccontextmanager
    async def refused(*_args, **_kwargs):
        raise httpx.ConnectError("Verbindung abgelehnt")
        yield  # pragma: no cover

    monkeypatch.setattr("services.agent_providers.admitted_stream", refused)

    result = await probe_capabilities(_profile())

    assert result["tools"] is None and "Verbindung abgelehnt" in result["error"]
    assert supports_tools(_profile(capabilities_json=result)) is True


def test_the_endpoint_stores_and_returns_the_check(client, db_session, monkeypatch):
    profile = AIProfile(
        name="Prüfprofil",
        kind="local",
        provider="ollama",
        protocol="ollama",
        llm_model="qwen3:8b",
        llm_base_url="http://ollama:11434",
        embedding_provider="ollama",
        embedding_model="bge-m3",
        embedding_dimension=1024,
        embedding_context_length=8192,
        llm_context_length=8192,
    )
    db_session.add(profile)
    db_session.commit()

    async def probe(checked):
        return {
            "model": checked.llm_model,
            "protocol": checked.protocol,
            "base_url": checked.llm_base_url,
            "tools": True,
            "error": None,
        }

    monkeypatch.setattr("api.ai_capabilities.probe_capabilities", probe)
    try:
        response = client.post(f"/ai-profiles/{profile.id}/capabilities")
        assert response.status_code == 200
        assert response.json()["capabilities"]["tools"] is True
        db_session.refresh(profile)
        assert profile.capabilities_json["tools"] is True
        listed = client.get("/ai-profiles").json()["profiles"]
        assert next(p for p in listed if p["id"] == profile.id)["capabilities"]["tools"] is True
    finally:
        db_session.delete(profile)
        db_session.commit()


def test_profile_capabilities_module_lists_every_adapter_protocol():
    assert profile_capabilities.AGENT_TOOL_PROTOCOLS == {
        "ollama",
        "openai_chat",
        "openai_responses",
        "anthropic",
        "gemini",
    }
