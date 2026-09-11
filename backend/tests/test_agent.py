"""Focused unit tests for O-168: Ollama-Kontextfenster und Werkzeugergebnis-Deckel
in der Agent-Werkzeugschleife (agent.py)."""

import contextlib
import json
from types import SimpleNamespace

import httpx
import pytest

import core.config as cfg
from agent import MAX_MCP_TOOL_RESULT_CHARS, _cap_tool_result, run_agent_loop


def test_cap_tool_result_leaves_short_text_untouched():
    text = "kurzes Ergebnis"
    assert _cap_tool_result(text) == text


def test_cap_tool_result_truncates_and_notes_how_much_was_removed():
    text = "x" * (MAX_MCP_TOOL_RESULT_CHARS + 500)

    capped = _cap_tool_result(text)

    assert len(capped) < len(text)
    assert capped.startswith("x" * MAX_MCP_TOOL_RESULT_CHARS)
    assert "500 weitere Zeichen entfernt" in capped


@pytest.mark.asyncio
async def test_ollama_agent_loop_sets_explicit_num_ctx(monkeypatch):
    """Ohne num_ctx faellt Ollama auf sein kleines, stillschweigend kuerzendes
    Default-Kontextfenster zurueck (siehe O-168) -- die Agent-Schleife muss es
    also explizit im Request-Payload setzen, genau wie stream_standard_rag_events."""
    captured = {}

    @contextlib.asynccontextmanager
    async def mock_stream(self, method, url, **kwargs):
        captured.update(payload=kwargs["json"])
        response = SimpleNamespace()
        response.raise_for_status = lambda: None

        async def lines():
            # Keine tool_calls im Delta -> Schleife endet nach der ersten Runde.
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Antwort"}}]})
            yield "data: [DONE]"

        response.aiter_lines = lines
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", mock_stream)

    events = [
        event
        async for event in run_agent_loop(
            provider="ollama",
            model_name="test-model",
            api_key=None,
            base_url=None,
            system_prompt="System",
            prompt="Frage",
            temperature=0.2,
            repo_id=None,
            db_session=SimpleNamespace(),
            mcp_clients=[],
            ollama_base_url="http://ollama:11434",
            project_id=1,  # schaltet das get_repo_entities-Werkzeug frei, ohne die DB zu berühren
        )
    ]

    assert captured["payload"]["num_ctx"] == cfg.OLLAMA_NUM_CTX
    assert [e["type"] for e in events][-1] == "answer"
