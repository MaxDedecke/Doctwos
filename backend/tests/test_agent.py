"""Focused unit tests for O-168: Ollama-Kontextfenster und Werkzeugergebnis-Deckel
in der Agent-Werkzeugschleife (agent.py)."""

import contextlib
import json
from types import SimpleNamespace

import httpx
import pytest

import core.config as cfg
from agent import (
    MAX_MCP_TOOL_RESULT_CHARS,
    _cap_tool_result,
    _tool_result_was_truncated,
    run_agent_loop,
)


def test_cap_tool_result_leaves_short_text_untouched():
    text = "kurzes Ergebnis"
    assert _cap_tool_result(text) == text


def test_cap_tool_result_truncates_and_notes_how_much_was_removed():
    text = "x" * (MAX_MCP_TOOL_RESULT_CHARS + 500)

    capped = _cap_tool_result(text)

    assert len(capped) < len(text)
    assert capped.startswith("x" * MAX_MCP_TOOL_RESULT_CHARS)
    assert "500 weitere Zeichen entfernt" in capped
    assert _tool_result_was_truncated(capped) is True


def test_tool_result_was_truncated_false_for_untouched_text():
    assert _tool_result_was_truncated("kurzes Ergebnis") is False


class _FakeMcpClient:
    """Duck-typed Ersatz für MCPClient (kein echtes Subprozess-Protokoll nötig,
    agent.py prüft nirgends per isinstance)."""

    name = "fake-mcp"

    def __init__(self, result_text: str):
        self._result_text = result_text

    async def list_tools(self):
        return [
            {
                "name": "big_lookup",
                "description": "Liefert ein übergroßes Ergebnis.",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]

    async def call_tool(self, tool_name, arguments):
        return {"content": [{"type": "text", "text": self._result_text}]}


@pytest.mark.asyncio
async def test_ollama_agent_loop_flags_truncated_mcp_result(monkeypatch):
    """O-168: ein zu großes MCP-Werkzeugergebnis muss sowohl im Live-SSE-Event
    als auch in agent_steps (spätere metadata_json) als 'truncated' markiert
    sein -- das treibt das immer sichtbare Badge in AgentSteps.tsx."""
    calls = {"n": 0}

    @contextlib.asynccontextmanager
    async def mock_stream(self, method, url, **kwargs):
        calls["n"] += 1
        response = SimpleNamespace()
        response.raise_for_status = lambda: None

        async def first_turn_lines():
            # Ein vollständiger Tool-Call in einem einzelnen Delta-Chunk.
            yield "data: " + json.dumps(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {"name": "big_lookup", "arguments": "{}"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            )
            yield "data: [DONE]"

        async def second_turn_lines():
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Fertig"}}]})
            yield "data: [DONE]"

        response.aiter_lines = first_turn_lines if calls["n"] == 1 else second_turn_lines
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", mock_stream)

    fake_mcp = _FakeMcpClient("x" * (MAX_MCP_TOOL_RESULT_CHARS + 1))

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
            mcp_clients=[fake_mcp],
            ollama_base_url="http://ollama:11434",
        )
    ]

    tool_result_events = [e for e in events if e["type"] == "tool_result"]
    assert len(tool_result_events) == 1
    assert tool_result_events[0]["truncated"] is True

    answer_event = events[-1]
    assert answer_event["type"] == "answer"
    steps = answer_event["agent_steps"]
    saved_tool_result = next(s for s in steps if s["type"] == "tool_result")
    assert saved_tool_result["truncated"] is True


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
    tool_names = {tool["function"]["name"] for tool in captured["payload"]["tools"]}
    assert {"get_repo_entities", "trace_call_flow"}.issubset(tool_names)
    assert [e["type"] for e in events][-1] == "answer"


@pytest.mark.asyncio
async def test_openai_compatible_agent_uses_profile_subpath(monkeypatch):
    captured = {}

    @contextlib.asynccontextmanager
    async def mock_stream(self, method, url, **kwargs):
        captured.update(url=url, headers=kwargs["headers"])
        response = SimpleNamespace()
        response.raise_for_status = lambda: None

        async def lines():
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Antwort"}}]})
            yield "data: [DONE]"

        response.aiter_lines = lines
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", mock_stream)

    events = [
        event
        async for event in run_agent_loop(
            provider="openai",
            model_name="remote-model",
            api_key="remote-secret",
            base_url="https://inference.internal:8443/tenant/v1",
            endpoint_path="/custom/chat/completions",
            system_prompt="System",
            prompt="Frage",
            temperature=0.2,
            repo_id=None,
            db_session=SimpleNamespace(),
            mcp_clients=[],
            project_id=1,
        )
    ]

    assert captured == {
        "url": "https://inference.internal:8443/tenant/v1/custom/chat/completions",
        "headers": {
            "Content-Type": "application/json",
            "Authorization": "Bearer remote-secret",
        },
    }
    assert events[-1]["type"] == "answer"


@pytest.mark.asyncio
async def test_openai_responses_agent_executes_function_call(monkeypatch):
    requests = []

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    async def mock_post(self, url, **kwargs):
        requests.append(json.loads(json.dumps(kwargs["json"])))
        if len(requests) == 1:
            return FakeResponse(
                {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-1",
                            "name": "big_lookup",
                            "arguments": "{}",
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Fertig"}],
                    }
                ],
                "output_text": "Fertig",
            }
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    events = [
        event
        async for event in run_agent_loop(
            provider="openai_responses",
            model_name="gpt-5.6-luna",
            api_key="secret",
            base_url="https://api.openai.com/v1",
            endpoint_path="/responses",
            system_prompt="System",
            prompt="Frage",
            temperature=0.2,
            repo_id=None,
            db_session=SimpleNamespace(),
            mcp_clients=[_FakeMcpClient("Ergebnis")],
        )
    ]

    assert events[-1]["type"] == "answer"
    assert events[-1]["content"] == "Fertig"
    assert any(event["type"] == "tool_call" for event in events)
    assert any(event["type"] == "tool_result" for event in events)
    assert requests[0]["tools"][0]["type"] == "function"
    assert requests[1]["input"][-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "Ergebnis",
    }
    assert "temperature" not in requests[0]
