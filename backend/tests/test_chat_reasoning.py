"""Reasoning-Kanal und Responses-Stream: Denken getrennt von der Antwort, je Protokoll."""

import contextlib
import json
from types import SimpleNamespace

import pytest

from services.agent_providers import Reasoning
from services.agent_providers_hosted import OpenAIResponsesAdapter, ResponsesStreamError
from services.standard_chat import stream_standard_rag_events
from services.think_filter import MAX_REASONING_STEP_CHARS, ThinkFilter, reasoning_step
from test_agent_model_robustness import _run, _serve, _sse


def test_inline_thinking_is_collected_instead_of_dropped():
    think_filter = ThinkFilter()
    shown = think_filter.feed("<think>erst prüfen</th") + think_filter.feed("ink>Antwort")
    assert shown == "Antwort"
    assert think_filter.take_reasoning() == "erst prüfen"

    think_filter = ThinkFilter()
    think_filter.feed("vorgefülltes Denken ")
    assert think_filter.feed("weiter</think>Antwort") == "Antwort"
    assert think_filter.take_reasoning() == "vorgefülltes Denken weiter"


def test_a_reasoning_step_is_bounded():
    step = reasoning_step(3, "x" * (MAX_REASONING_STEP_CHARS + 50))
    assert step["type"] == "reasoning" and step["turn"] == 3
    assert len(step["content"]) <= MAX_REASONING_STEP_CHARS + 4
    assert reasoning_step(0, "  ") is None


@pytest.mark.asyncio
async def test_ollama_thinking_is_streamed_live_and_kept_as_a_step(monkeypatch):
    line = {"message": {"thinking": "Ich prüfe", "content": "Antwort"}, "done": True}
    _serve(monkeypatch, [[json.dumps(line)]])

    events = await _run("ollama")

    assert {"type": "reasoning_chunk", "turn": 0, "content": "Ich prüfe"} in events
    answer = events[-1]
    assert answer["content"] == "Antwort"
    assert {"type": "reasoning", "turn": 0, "content": "Ich prüfe"} in answer["agent_steps"]


@pytest.mark.asyncio
async def test_chat_completions_reasoning_fields_are_a_separate_channel(monkeypatch):
    _serve(
        monkeypatch,
        [_sse({"reasoning_content": "Überlegung"})[:1] + _sse({"content": "Antwort"})],
    )

    events = await _run("vllm")

    assert any(e["type"] == "reasoning_chunk" and e["content"] == "Überlegung" for e in events)
    assert events[-1]["content"] == "Antwort"


@pytest.mark.asyncio
async def test_the_standard_chat_returns_thinking_as_a_step_not_as_answer(monkeypatch):
    @contextlib.asynccontextmanager
    async def mock_stream(_client, _url, **_kwargs):
        async def lines():
            yield json.dumps({"message": {"content": "<think>still</think>Hallo"}, "done": True})

        yield SimpleNamespace(is_success=True, aiter_lines=lines)

    monkeypatch.setattr("services.standard_chat.admitted_stream", mock_stream)

    events = [
        event
        async for event in stream_standard_rag_events(
            provider="ollama",
            model="m",
            api_key=None,
            base_url=None,
            temperature=None,
            system_prompt="S",
            history=[],
            prompt="Frage",
        )
    ]

    assert [e["content"] for e in events if e["type"] == "content_chunk"] == ["Hallo"]
    assert {"type": "reasoning_chunk", "turn": 0, "content": "still"} in events
    assert events[-1]["agent_steps"] == [{"type": "reasoning", "turn": 0, "content": "still"}]


def _responses_adapter(**overrides) -> OpenAIResponsesAdapter:
    arguments = dict(
        api_key="k",
        base_url="https://api.openai.com/v1",
        endpoint_path="/responses",
        model_name="gpt-6-luna",
        system_prompt="System",
        tools=[{"name": "lookup", "description": "", "inputSchema": {"type": "object"}}],
        history=[],
        prompt="Frage",
        temperature=None,
    )
    arguments.update(overrides)
    return OpenAIResponsesAdapter(**arguments)


def _serve_responses(monkeypatch, events: list[dict]) -> list[dict]:
    requests = []

    @contextlib.asynccontextmanager
    async def mock_stream(_client, _url, **kwargs):
        requests.append(kwargs["json"])

        async def lines():
            for event in events:
                yield "data: " + json.dumps(event)

        yield SimpleNamespace(is_success=True, aiter_lines=lines)

    monkeypatch.setattr("services.agent_providers_hosted.admitted_stream", mock_stream)
    return requests


async def _complete(adapter) -> list:
    return [item async for item in adapter.complete(None, 0, None)]


@pytest.mark.asyncio
async def test_responses_stream_text_and_reasoning_summary(monkeypatch):
    output = [{"type": "message", "content": [{"type": "output_text", "text": "Antwort"}]}]
    requests = _serve_responses(
        monkeypatch,
        [
            {"type": "response.reasoning_summary_text.delta", "delta": "Kurz gedacht"},
            {"type": "response.output_text.delta", "delta": "Ant"},
            {"type": "response.output_text.delta", "delta": "wort"},
            {
                "type": "response.completed",
                "response": {
                    "status": "completed",
                    "output": output,
                    "usage": {"input_tokens": 12},
                },
            },
        ],
    )

    items = await _complete(_responses_adapter(reasoning_summary=True))

    assert items[:3] == [Reasoning("Kurz gedacht"), "Ant", "wort"]
    turn = items[-1]
    assert turn.text == "Antwort" and turn.reasoning == "Kurz gedacht" and turn.prompt_tokens == 12
    assert requests[0]["stream"] is True and requests[0]["reasoning"] == {"summary": "auto"}


@pytest.mark.asyncio
async def test_a_responses_stream_without_completion_is_an_error(monkeypatch):
    _serve_responses(monkeypatch, [{"type": "response.output_text.delta", "delta": "Ant"}])

    with pytest.raises(ResponsesStreamError):
        await _complete(_responses_adapter())


def test_responses_input_obeys_the_context_window():
    history = [{"role": "user", "content": "alt " * 3000}, {"role": "assistant", "content": "a"}]
    adapter = _responses_adapter(history=history, context_length=2048)
    adapter.add_tool_results(
        [SimpleNamespace(id="c1", name="lookup", arguments={})], ["Ergebnis " * 2000], None
    )

    adapter._fit_messages()

    assert adapter.take_context_cut() == ["history", "tool_results"]
    assert all(item.get("content") != history[0]["content"] for item in adapter.input)
    output = next(item for item in adapter.input if item.get("type") == "function_call_output")
    assert output["output"].endswith("passt]")
