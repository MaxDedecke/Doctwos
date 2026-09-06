"""Focused unit tests for router-independent chat service behavior."""

import contextlib
import json
from types import SimpleNamespace

import httpx
import pytest

from services.chat_service import (
    build_chat_prompt,
    build_pinned_context,
    stream_standard_rag_events,
)


def test_prompt_keeps_the_pinned_file_as_primary_context():
    prompt = build_chat_prompt(
        context="<untrusted_source>other file</untrusted_source>",
        pinned_context="<untrusted_pinned_code>focused</untrusted_pinned_code>",
        message="What does it do?",
        pinned_file="src/payroll.cbl",
        multi_project_names=[],
    )

    assert "pinned code as the primary subject" in prompt
    assert "Question: What does it do?" in prompt
    assert "<untrusted_context>" in prompt


def test_non_file_focus_is_included_without_repository_context():
    context = build_pinned_context(
        pinned_file=None,
        pinned_line=None,
        pinned_label=None,
        pinned_context="IFC space: server room",
        pinned_chunks=[],
        repository_id=None,
    )

    assert "<untrusted_focused_object>" in context
    assert "IFC space: server room" in context


@pytest.mark.asyncio
async def test_standard_rag_stream_normalizes_openai_events(monkeypatch):
    captured = {}

    @contextlib.asynccontextmanager
    async def mock_stream(self, method, url, **kwargs):
        captured.update(method=method, url=url, payload=kwargs["json"])
        response = SimpleNamespace()
        response.raise_for_status = lambda: None

        async def lines():
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Hallo"}}]})
            yield "data: " + json.dumps({"choices": [{"delta": {"content": " Welt"}}]})
            yield "data: [DONE]"

        response.aiter_lines = lines
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", mock_stream)
    events = [
        event
        async for event in stream_standard_rag_events(
            provider="openai",
            model="test-model",
            api_key="test-key",
            base_url="https://llm.example/v1",
            temperature=0.2,
            system_prompt="System",
            history=[SimpleNamespace(role="user", content="Vorher")],
            prompt="Frage",
        )
    ]

    assert captured["method"] == "POST"
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    assert captured["payload"]["messages"][-1] == {"role": "user", "content": "Frage"}
    assert [event["type"] for event in events] == [
        "content_chunk",
        "content_chunk",
        "turn_completed",
        "answer",
    ]
    assert events[-1]["content"] == "Hallo Welt"
