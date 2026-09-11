"""Focused unit tests for router-independent chat service behavior."""

import contextlib
import json
from types import SimpleNamespace

import httpx
import pytest

import core.config as cfg
from services.chat_service import (
    build_chat_prompt,
    build_pinned_context,
    stream_standard_rag_events,
)


def _fake_chunk(start_line, end_line, content):
    return SimpleNamespace(
        start_line=start_line,
        end_line=end_line,
        content=content,
        metadata_json=None,
        file_path="cbl/PROGRAM.cbl",
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


def test_line_focus_only_excerpts_a_small_window_not_the_whole_chunk():
    """O-090: a bare gutter-line focus must not hand the model the whole chunk
    the line happens to sit in — only a small window around it."""
    lines = [f"LINE-{n:03d}." for n in range(1, 51)]
    chunk = _fake_chunk(1, 50, "\n".join(lines))

    context = build_pinned_context(
        pinned_file="cbl/PROGRAM.cbl",
        pinned_line=30,
        pinned_label=None,
        pinned_context=None,
        pinned_chunks=[chunk],
        repository_id=None,
    )

    assert "LINE-030." in context
    assert "LINE-015." in context and "LINE-045." in context  # +/- 15 window edges
    assert "LINE-001." not in context and "LINE-050." not in context
    assert "More surrounding code exists" in context


def test_entity_focus_excerpts_exactly_its_own_line_range():
    """O-090: an entity focus (end_line set) gets exactly its own physical
    bounds as the excerpt, even when the underlying chunk spans more than
    that (e.g. several paragraphs merged into one chunk)."""
    lines = [f"LINE-{n:03d}." for n in range(1, 51)]
    merged_chunk = _fake_chunk(1, 50, "\n".join(lines))

    context = build_pinned_context(
        pinned_file="cbl/PROGRAM.cbl",
        pinned_line=10,
        pinned_end_line=20,
        pinned_label="MY-PARAGRAPH",
        pinned_context=None,
        pinned_chunks=[merged_chunk],
        repository_id=None,
    )

    assert "LINE-010." in context and "LINE-020." in context
    assert "LINE-009." not in context and "LINE-021." not in context
    assert "More surrounding code exists" in context


def test_entity_focus_spanning_the_whole_chunk_has_no_more_context_note():
    """When the focused object's bounds exactly match the fetched chunk(s),
    there is nothing left outside the excerpt to warn about."""
    lines = [f"LINE-{n:03d}." for n in range(1, 6)]
    chunk = _fake_chunk(1, 5, "\n".join(lines))

    context = build_pinned_context(
        pinned_file="cbl/PROGRAM.cbl",
        pinned_line=1,
        pinned_end_line=5,
        pinned_label="SHORT-PARAGRAPH",
        pinned_context=None,
        pinned_chunks=[chunk],
        repository_id=None,
    )

    assert "LINE-001." in context and "LINE-005." in context
    assert "More surrounding code exists" not in context


def test_whole_file_pin_without_a_line_still_dumps_full_chunks():
    """Pinning a whole file/document (no line, e.g. clicking a sidebar file)
    is unaffected by the O-090 windowing — the user asked about the whole thing."""
    chunk = _fake_chunk(1, 3, "FULL CONTENT")

    context = build_pinned_context(
        pinned_file="docs/spec.md",
        pinned_line=0,
        pinned_label=None,
        pinned_context=None,
        pinned_chunks=[chunk],
        repository_id=None,
    )

    assert "FULL CONTENT" in context
    assert "More surrounding code exists" not in context


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


@pytest.mark.asyncio
async def test_ollama_stream_sets_explicit_num_ctx(monkeypatch):
    """O-168: ohne num_ctx faellt Ollama auf sein kleines, stillschweigend
    kuerzendes Default-Kontextfenster zurueck."""
    captured = {}

    @contextlib.asynccontextmanager
    async def mock_stream(self, method, url, **kwargs):
        captured.update(payload=kwargs["json"])
        response = SimpleNamespace()
        response.raise_for_status = lambda: None

        async def lines():
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Hi"}}]})
            yield "data: [DONE]"

        response.aiter_lines = lines
        yield response

    monkeypatch.setattr(httpx.AsyncClient, "stream", mock_stream)
    [
        event
        async for event in stream_standard_rag_events(
            provider="ollama",
            model="test-model",
            api_key=None,
            base_url=None,
            temperature=0.2,
            system_prompt="System",
            history=[],
            prompt="Frage",
        )
    ]

    assert captured["payload"]["num_ctx"] == cfg.OLLAMA_NUM_CTX
