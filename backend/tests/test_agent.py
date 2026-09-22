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
    find_repo_files,
    list_repo_files,
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


def test_source_wide_file_lookup_reaches_deep_paths_and_omits_git_metadata(monkeypatch, tmp_path):
    target = tmp_path / "app" / "transaction" / "db2" / "cbl" / "COTRTLIC.cbl"
    target.parent.mkdir(parents=True)
    target.write_text("IDENTIFICATION DIVISION.\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("private metadata", encoding="utf-8")
    monkeypatch.setattr(
        "agent.get_repo_path",
        lambda _repo_id, file_path="": str(tmp_path / file_path) if file_path else str(tmp_path),
    )

    assert find_repo_files(1, "COTRTLIC.cbl") == ["app/transaction/db2/cbl/COTRTLIC.cbl"]
    assert list_repo_files(1)["files"] == ["app/transaction/db2/cbl/COTRTLIC.cbl"]


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
    captured = {"payloads": []}

    @contextlib.asynccontextmanager
    async def mock_stream(self, method, url, **kwargs):
        captured["payloads"].append(kwargs["json"])
        response = SimpleNamespace()
        response.raise_for_status = lambda: None

        async def lines():
            # Keine tool_calls im Delta -> Schleife endet nach der ersten Runde.
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Antwort"}}]})
            yield "data: [DONE]"

        response.aiter_lines = lines
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", mock_stream)

    @contextlib.asynccontextmanager
    async def mock_admitted_stream(client, url, **kwargs):
        async with client.stream("POST", url, json=kwargs["json"], headers=kwargs["headers"]) as response:
            yield response

    monkeypatch.setattr("agent.admitted_stream", mock_admitted_stream)

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
            require_initial_tool_call=True,
        )
    ]

    assert all(payload["num_ctx"] == cfg.OLLAMA_NUM_CTX for payload in captured["payloads"])
    # Project turns now receive a deterministic repository bootstrap before the
    # first model request, so the model can choose follow-up tools normally.
    assert all(payload.get("tool_choice") is None for payload in captured["payloads"])
    tool_names = {tool["function"]["name"] for tool in captured["payloads"][0]["tools"]}
    assert {"get_repo_entities", "trace_call_flow"}.issubset(tool_names)
    assert [e["type"] for e in events][-1] == "answer"


@pytest.mark.asyncio
async def test_ollama_agent_bootstraps_pinned_file_before_model(monkeypatch, tmp_path):
    """A pinned repository question must have deterministic file evidence even
    when the Ollama endpoint ignores ``tool_choice=required``."""
    (tmp_path / "config.sh").write_text("#!/bin/sh\nMODE=prod\n", encoding="utf-8")
    captured = {}

    monkeypatch.setattr("agent.get_repo_path", lambda _repo_id, _file_path="": str(tmp_path / _file_path) if _file_path else str(tmp_path))

    @contextlib.asynccontextmanager
    async def mock_stream(self, method, url, **kwargs):
        captured["payload"] = kwargs["json"]
        response = SimpleNamespace()
        response.raise_for_status = lambda: None

        async def lines():
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Belegt."}}]})
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
            prompt="Was passiert hier?",
            temperature=0.2,
            repo_id=1,
            db_session=SimpleNamespace(),
            mcp_clients=[],
            ollama_base_url="http://ollama:11434",
            project_id=1,
            pinned_file="config.sh",
            pinned_line=2,
            require_initial_tool_call=True,
        )
    ]

    assert [event["type"] for event in events[:2]] == ["tool_call", "tool_result"]
    assert events[0]["name"] == "view_repo_file"
    bootstrap_call = captured["payload"]["messages"][2]["tool_calls"][0]
    assert '"file_path": "config.sh"' in bootstrap_call["function"]["arguments"]
    assert captured["payload"]["messages"][3]["role"] == "tool"
    assert "tool_choice" not in captured["payload"]
    assert events[-1]["type"] == "answer"
    assert any(step["type"] == "tool_result" for step in events[-1]["agent_steps"])


@pytest.mark.asyncio
async def test_ollama_agent_bootstraps_exact_entities_inside_explicit_file_scope(monkeypatch, tmp_path):
    target = tmp_path / "core" / "UserServiceImpl.java"
    target.parent.mkdir()
    target.write_text("class UserServiceImpl {}\n", encoding="utf-8")
    captured = {}

    monkeypatch.setattr(
        "agent.get_repo_path",
        lambda _repo_id, _file_path="": str(tmp_path / _file_path) if _file_path else str(tmp_path),
    )
    monkeypatch.setattr(
        "agent.get_repo_entities",
        lambda _project_id, _db, query="", limit=80, file_paths=None, entity_names=None: {
            "entities": [], "file_paths": file_paths, "entity_names": entity_names
        },
    )

    @contextlib.asynccontextmanager
    async def mock_stream(self, method, url, **kwargs):
        captured["payload"] = kwargs["json"]
        response = SimpleNamespace()
        response.raise_for_status = lambda: None

        async def lines():
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Keine Kante."}}]})
            yield "data: [DONE]"

        response.aiter_lines = lines
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", mock_stream)

    @contextlib.asynccontextmanager
    async def mock_admitted_stream(client, url, **kwargs):
        async with client.stream("POST", url, json=kwargs["json"], headers=kwargs["headers"]) as response:
            yield response

    monkeypatch.setattr("agent.admitted_stream", mock_admitted_stream)

    events = [
        event
        async for event in run_agent_loop(
            provider="ollama",
            model_name="test-model",
            api_key=None,
            base_url=None,
            system_prompt="System",
            prompt="Question: Verfolge `UserServiceImpl.create`.",
            temperature=0.2,
            repo_id=1,
            db_session=SimpleNamespace(),
            mcp_clients=[],
            ollama_base_url="http://ollama:11434",
            project_id=1,
            require_initial_tool_call=True,
        )
    ]

    assert events[0]["name"] == "get_repo_entities"
    assert events[0]["arguments"]["entity_names"] == ["UserServiceImpl", "create"]
    assert events[0]["arguments"]["file_paths"] == ["core/UserServiceImpl.java"]


@pytest.mark.asyncio
async def test_trace_call_flow_rejects_an_entity_outside_exact_resolution(monkeypatch, tmp_path):
    target = tmp_path / "core" / "UserServiceImpl.java"
    target.parent.mkdir()
    target.write_text("class UserServiceImpl {}\n", encoding="utf-8")
    calls = {"count": 0}
    monkeypatch.setattr(
        "agent.get_repo_path",
        lambda _repo_id, file_path="": str(tmp_path / file_path) if file_path else str(tmp_path),
    )
    monkeypatch.setattr(
        "agent.get_repo_entities",
        lambda *_args, **_kwargs: {
            "entities": [
                {
                    "id": 17,
                    "name": "create",
                    "qualified_name": "demo.UserServiceImpl#create()",
                    "file_path": "core/UserServiceImpl.java",
                }
            ]
        },
    )

    @contextlib.asynccontextmanager
    async def mock_admitted_stream(_client, _url, **_kwargs):
        calls["count"] += 1
        response = SimpleNamespace()
        response.raise_for_status = lambda: None

        async def lines():
            if calls["count"] == 1:
                yield "data: " + json.dumps(
                    {"choices": [{"delta": {"tool_calls": [{
                        "index": 0,
                        "id": "trace-1",
                        "type": "function",
                        "function": {"name": "trace_call_flow", "arguments": '{"entity_id": 99}'},
                    }]}}]}
                )
            else:
                yield "data: " + json.dumps({"choices": [{"delta": {"content": "Keine belegte Kante."}}]})
            yield "data: [DONE]"

        response.aiter_lines = lines
        yield response

    monkeypatch.setattr("agent.admitted_stream", mock_admitted_stream)

    events = [
        event
        async for event in run_agent_loop(
            provider="ollama",
            model_name="test-model",
            api_key=None,
            base_url=None,
            system_prompt="System",
            prompt="Question: Verfolge `UserServiceImpl.create`.",
            temperature=0.2,
            repo_id=1,
            db_session=SimpleNamespace(),
            mcp_clients=[],
            ollama_base_url="http://ollama:11434",
            project_id=1,
            require_initial_tool_call=True,
        )
    ]

    trace_result = next(event for event in events if event.get("id") == "trace-1" and event["type"] == "tool_result")
    assert "entity_not_exactly_resolved" in trace_result["result"]


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
