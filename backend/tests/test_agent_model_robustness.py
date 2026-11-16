"""Verhalten der Agentenschleife bei den Schwächen lokaler Modellserver (Qwen an Ollama, vLLM, llama.cpp):
leere Züge, ungültige Werkzeugargumente, Denkabschnitte im Text, volles Kontextfenster."""

import contextlib
import json
from types import SimpleNamespace

import pytest

import core.config as cfg
from agent import run_agent_loop
from services.agent_providers import (
    _TRIMMED_TOOL_RESULT,
    OllamaChatAdapter,
    OpenAIChatAdapter,
    ThinkFilter,
    ToolCall,
    strip_thinking,
)
from services.agent_tool_defs import local_tool_definitions
from services.agent_tool_executor import AgentToolExecutor
from services.chat_service import stream_standard_rag_events
from services.chat_turn import ChatSseTelemetry


class _FakeMcpClient:
    name = "fake-mcp"

    async def list_tools(self):
        return [{"name": "lookup", "description": "", "inputSchema": {"type": "object"}}]

    async def call_tool(self, _name, _arguments):
        return {"content": [{"type": "text", "text": "Ergebnis"}]}


def _ollama_line(*, text: str = "", call: str | None = None, prompt_tokens: int = 40) -> str:
    message: dict = {"role": "assistant", "content": text}
    if call:
        message["tool_calls"] = [{"id": "call-1", "function": {"name": call, "arguments": {}}}]
    return json.dumps(
        {
            "message": message,
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": prompt_tokens,
            "eval_count": 5,
        }
    )


def _sse(delta: dict, **extra) -> list[str]:
    return ["data: " + json.dumps({"choices": [{"delta": delta}], **extra}), "data: [DONE]"]


def _sse_call(arguments: str) -> list[str]:
    call = {"index": 0, "id": "call-1", "type": "function"}
    return _sse({"tool_calls": [{**call, "function": {"name": "lookup", "arguments": arguments}}]})


def _serve(monkeypatch, replies: list[list[str]]) -> list[dict]:
    """Ersetzt den Modellaufruf durch feste Antwortzeilen; liefert die gesendeten Anfragen."""
    requests: list[dict] = []

    @contextlib.asynccontextmanager
    async def mock_admitted_stream(_client, url, **kwargs):
        requests.append({"url": url, **json.loads(json.dumps(kwargs["json"]))})
        lines = replies[len(requests) - 1]
        response = SimpleNamespace(is_success=True)

        async def aiter_lines():
            for line in lines:
                yield line

        response.aiter_lines = aiter_lines
        yield response

    monkeypatch.setattr("services.agent_providers.admitted_stream", mock_admitted_stream)
    return requests


async def _run(provider: str, **overrides) -> list[dict]:
    arguments = dict(
        provider=provider,
        model_name="test-model",
        api_key=None,
        base_url="http://vllm:8000/v1",
        system_prompt="System",
        prompt="Frage",
        temperature=None,
        repo_id=None,
        db_session=SimpleNamespace(),
        mcp_clients=[_FakeMcpClient()],
        ollama_base_url="http://ollama:11434",
    )
    arguments.update(overrides)
    return [event async for event in run_agent_loop(**arguments)]


@pytest.mark.parametrize(
    "pieces, expected",
    [
        (["<think>erst überlegen</think>Antwort"], "Antwort"),
        (["<thi", "nk>über", "legen</th", "ink>Ant", "wort"], "Antwort"),
        (["Text mit a < b und <tag>"], "Text mit a < b und <tag>"),
        (["Antwort<think>nie geschlossen"], "Antwort"),
    ],
)
def test_think_filter_removes_thinking_across_chunk_boundaries(pieces, expected):
    think_filter = ThinkFilter()
    assert "".join(think_filter.feed(piece) for piece in pieces) + think_filter.flush() == expected


def test_strip_thinking_treats_text_before_a_lone_closing_tag_as_thinking():
    assert strip_thinking("überlegen, überlegen</think>\n\nAntwort") == "Antwort"
    assert strip_thinking("<think>a</think>Eins <think>b</think>Zwei") == "Eins Zwei"
    assert strip_thinking("Kein Denken") == "Kein Denken"


@pytest.mark.asyncio
async def test_ollama_agent_uses_the_native_chat_path_with_the_profile_context(monkeypatch):
    """Ollamas /v1/chat/completions kennt kein num_ctx; nur /api/chat nimmt es in options an."""
    requests = _serve(monkeypatch, [[_ollama_line(call="lookup")], [_ollama_line(text="Antwort")]])

    events = await _run("ollama", temperature=0.6, context_length=32768)

    assert [r["url"] for r in requests] == ["http://ollama:11434/api/chat"] * 2
    assert all(r["options"] == {"temperature": 0.6, "num_ctx": 32768} for r in requests)
    assert all("num_ctx" not in r and "temperature" not in r for r in requests)
    assert all("tool_choice" not in r for r in requests)
    assistant, tool = requests[1]["messages"][-2:]
    assert assistant["tool_calls"][0]["function"] == {"name": "lookup", "arguments": {}}
    assert tool == {
        "role": "tool",
        "tool_call_id": "call-1",
        "tool_name": "lookup",
        "content": "Ergebnis",
    }
    assert events[-1]["content"] == "Antwort"


@pytest.mark.asyncio
async def test_ollama_agent_falls_back_to_the_configured_context_without_a_profile_value(
    monkeypatch,
):
    requests = _serve(monkeypatch, [[_ollama_line(text="Antwort")]])

    await _run("ollama")

    assert requests[0]["options"]["num_ctx"] == cfg.OLLAMA_NUM_CTX


@pytest.mark.asyncio
async def test_ollama_final_turn_offers_no_tools_because_tool_choice_is_not_supported(
    monkeypatch,
):
    monkeypatch.setattr("agent.MAX_AGENT_TURNS", 2)
    requests = _serve(monkeypatch, [[_ollama_line(call="lookup")], [_ollama_line(text="Fazit")]])

    events = await _run("ollama")

    assert "tools" in requests[0] and "tools" not in requests[1]
    assert events[-1]["content"] == "Fazit"


@pytest.mark.asyncio
async def test_an_empty_model_turn_is_retried_once(monkeypatch):
    """Server verwerfen einen Werkzeugaufruf mit ungültigem JSON still und liefern dann nichts."""
    requests = _serve(monkeypatch, [[_ollama_line()], [_ollama_line(text="Antwort")]])

    events = await _run("ollama")

    assert len(requests) == 2
    assert events[-1] == {**events[-1], "type": "answer", "content": "Antwort"}


@pytest.mark.asyncio
async def test_a_second_empty_model_turn_ends_with_an_empty_answer(monkeypatch):
    requests = _serve(monkeypatch, [[_ollama_line()], [_ollama_line()]])

    events = await _run("ollama")

    assert len(requests) == 2
    assert events[-1]["type"] == "answer" and events[-1]["content"] == ""


@pytest.mark.asyncio
async def test_invalid_tool_arguments_are_reported_to_the_model_instead_of_ending_the_run(
    monkeypatch,
):
    requests = _serve(
        monkeypatch,
        [
            _sse_call("{\"query\": \\'x\\'}"),
            _sse_call('{"query": "x"}'),
            _sse({"content": "Antwort"}),
        ],
    )

    events = await _run("vllm")

    results = [e["result"] for e in events if e["type"] == "tool_result"]
    assert "kein gültiges JSON-Objekt" in results[0]
    assert results[1] == "Ergebnis"
    # Die ungültigen Argumente gehen nicht zurück an den Server; er würde die Anfrage ablehnen.
    resent = requests[1]["messages"][-2]["tool_calls"][0]["function"]["arguments"]
    assert json.loads(resent) == {}
    assert events[-1]["content"] == "Antwort"


@pytest.mark.asyncio
async def test_openai_compatible_agent_strips_inline_thinking_and_reports_usage(monkeypatch):
    usage = {"prompt_tokens": 1234, "completion_tokens": 56}
    requests = _serve(
        monkeypatch,
        [
            [
                "data: " + json.dumps({"choices": [{"delta": {"content": "<think>Plan"}}]}),
                "data: " + json.dumps({"choices": [{"delta": {"content": "</think>Antwort"}}]}),
                "data: "
                + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": usage}),
                "data: [DONE]",
            ]
        ],
    )

    events = await _run("vllm")

    assert requests[0]["stream_options"] == {"include_usage": True}
    assert "".join(e["content"] for e in events if e["type"] == "content_chunk") == "Antwort"
    assert events[-1]["content"] == "Antwort"
    assert [e for e in events if e["type"] == "model_usage"] == [
        {
            "type": "model_usage",
            "turn": 0,
            "prompt_tokens": 1234,
            "completion_tokens": 56,
            "finish_reason": "stop",
        }
    ]


@pytest.mark.parametrize("adapter_class", [OpenAIChatAdapter, OllamaChatAdapter])
def test_older_tool_results_are_dropped_before_the_context_window_overflows(adapter_class):
    """Das erste Ergebnis (vorab geladenes Belegpaket) und das jüngste bleiben stehen."""
    conversation = dict(
        model_name="m",
        system_prompt="System",
        tools=[],
        history=[],
        prompt="Frage",
        temperature=0.2,
        context_length=4000,
    )
    if adapter_class is OllamaChatAdapter:
        adapter = adapter_class(
            api_key=None, endpoint_path=None, ollama_base_url="http://ollama:11434", **conversation
        )
    else:
        adapter = adapter_class(
            provider="vllm",
            api_key=None,
            base_url="http://vllm/v1",
            endpoint_path=None,
            **conversation,
        )
    for index in range(4):
        call = ToolCall(f"c{index}", "lookup", {})
        adapter.add_tool_results([call], [f"Ergebnis {index} " + "x" * 3000], None)

    adapter._fit_messages()

    contents = [m["content"] for m in adapter.messages if m["role"] == "tool"]
    assert contents[0].startswith("Ergebnis 0") and contents[3].startswith("Ergebnis 3")
    assert contents[1] == contents[2] == _TRIMMED_TOOL_RESULT


def test_tool_results_stay_untouched_while_the_conversation_fits():
    adapter = OpenAIChatAdapter(
        provider="vllm",
        api_key=None,
        base_url="http://vllm/v1",
        endpoint_path=None,
        model_name="m",
        system_prompt="System",
        tools=[],
        history=[],
        prompt="Frage",
        temperature=0.2,
        context_length=32768,
    )
    for index in range(4):
        adapter.add_tool_results([ToolCall(f"c{index}", "lookup", {})], ["x" * 3000], None)

    adapter._fit_messages()

    assert all(m["content"] == "x" * 3000 for m in adapter.messages if m["role"] == "tool")


def test_answer_context_is_offered_wherever_the_bootstrap_shows_it_as_a_call():
    names = [tool["name"] for tool in local_tool_definitions(False, [], project_id=1)]
    assert "answer_context" in names
    assert "answer_context" not in [t["name"] for t in local_tool_definitions(False, [], None)]
    described = json.dumps(local_tool_definitions(True, [{"chunk_id": 1}], 1))
    assert "explain_symbol" not in described


@pytest.mark.asyncio
async def test_answer_context_tool_builds_the_evidence_pack_for_the_named_symbols(monkeypatch):
    captured = {}

    def fake_build(db, user, project_id, **kwargs):
        captured.update(user=user, project_id=project_id, **kwargs)
        return {"resolved": [{"symbol": "CBACT04C"}], "evidence": []}

    monkeypatch.setattr("services.answer_context.build_answer_context", fake_build)
    user = SimpleNamespace(id=7)
    query = SimpleNamespace(filter=lambda *_: SimpleNamespace(first=lambda: user))
    executor = AgentToolExecutor(
        repo_id=None,
        repo_available=False,
        project_id=3,
        db_session=SimpleNamespace(query=lambda _model: query),
        audit_user_id=7,
        audit_chat_session_id=None,
        audit_chat_message_id=None,
        walkthrough_documents=[],
        mcp_tool_map={},
        prompt="Frage",
        evidence_chars=9000,
    )

    result = await executor.execute("answer_context", {"symbols": ["CBACT04C"], "topic": "Zinsen"})

    assert json.loads(result)["resolved"] == [{"symbol": "CBACT04C"}]
    assert captured == {
        "user": user,
        "project_id": 3,
        "symbols": ["CBACT04C"],
        "topic": "Zinsen",
        "max_chars": 9000,
    }
    rejected = await executor.execute("answer_context", {"symbols": "CBACT04C"})
    assert "error" in json.loads(rejected)


@pytest.mark.asyncio
async def test_standard_chat_sends_the_ollama_temperature_inside_options(monkeypatch):
    """Ollamas /api/chat ignoriert ein temperature-Feld auf oberster Ebene."""
    captured = {}

    @contextlib.asynccontextmanager
    async def mock_admitted_stream(_client, _url, **kwargs):
        captured.update(kwargs["json"])
        response = SimpleNamespace(is_success=True)

        async def aiter_lines():
            yield json.dumps({"message": {"content": "Hi"}, "done": True})

        response.aiter_lines = aiter_lines
        yield response

    monkeypatch.setattr("services.chat_service.admitted_stream", mock_admitted_stream)
    events = [
        event
        async for event in stream_standard_rag_events(
            provider="ollama",
            model="test-model",
            api_key=None,
            base_url="http://ollama:11434",
            temperature=0.6,
            system_prompt="System",
            history=[],
            prompt="Frage",
            context_length=16384,
        )
    ]

    assert captured["options"] == {"temperature": 0.6, "num_ctx": 16384}
    assert "temperature" not in captured
    assert events[-1]["content"] == "Hi"


@pytest.mark.asyncio
async def test_standard_chat_strips_inline_thinking_from_stream_and_answer(monkeypatch):
    @contextlib.asynccontextmanager
    async def mock_admitted_stream(_client, _url, **_kwargs):
        response = SimpleNamespace(is_success=True)

        async def aiter_lines():
            for piece in ("<think>Pl", "an</think>", "Hallo"):
                yield "data: " + json.dumps({"choices": [{"delta": {"content": piece}}]})
            yield "data: [DONE]"

        response.aiter_lines = aiter_lines
        yield response

    monkeypatch.setattr("services.chat_service.admitted_stream", mock_admitted_stream)
    events = [
        event
        async for event in stream_standard_rag_events(
            provider="vllm",
            model="Qwen/Qwen3-32B",
            api_key=None,
            base_url="http://vllm:8000/v1",
            temperature=None,
            system_prompt="System",
            history=[],
            prompt="Frage",
            protocol="openai_chat",
        )
    ]

    assert "".join(e["content"] for e in events if e["type"] == "content_chunk") == "Hallo"
    assert events[-1]["content"] == "Hallo"


def test_telemetry_keeps_the_fullest_prompt_and_the_generated_tokens():
    telemetry = ChatSseTelemetry(0.0)
    telemetry.record_model_usage({"prompt_tokens": 6000, "completion_tokens": 300})
    telemetry.record_model_usage({"prompt_tokens": 9500, "completion_tokens": 200})
    telemetry.record_model_usage({"prompt_tokens": None, "completion_tokens": None})

    metrics = telemetry.metrics()
    assert metrics["model_turns"] == 3
    assert metrics["prompt_tokens_max"] == 9500
    assert metrics["completion_tokens"] == 500


# --- Kontextfenster: Frage bleibt stehen, Grundlast klein, Überlauf sichtbar ---


def _budget_adapter(context_length: int, *, history=(), prompt="Frage") -> OllamaChatAdapter:
    return OllamaChatAdapter(
        api_key=None,
        endpoint_path=None,
        ollama_base_url="http://ollama:11434",
        model_name="m",
        system_prompt="System",
        tools=[],
        history=list(history),
        prompt=prompt,
        temperature=0.2,
        context_length=context_length,
    )


def _prompt_with_context(context: str, question: str) -> str:
    return f"Context:\n<untrusted_context>\n{context}\n</untrusted_context>\n\nQuestion: {question}\nAnswer:"


def test_the_question_survives_when_history_context_and_evidence_exceed_the_window():
    """Ollama strich bei Überlauf Verlauf und Frage und ließ nur das Werkzeugergebnis stehen."""
    history = [
        {"role": "user", "content": "alt " * 800},
        {"role": "assistant", "content": "x" * 3000},
    ]
    adapter = _budget_adapter(
        4000, history=history, prompt=_prompt_with_context("K" * 9000, "Was macht CBACT04C?")
    )
    adapter.add_tool_results([ToolCall("bootstrap-0", "answer_context", {})], ["B" * 6000], None)

    assert adapter._fit_messages() is True

    roles = [m["role"] for m in adapter.messages]
    assert roles == ["system", "user", "assistant", "tool"]  # Verlauf ist weg
    prompt = adapter.messages[1]["content"]
    assert prompt.endswith("Question: Was macht CBACT04C?\nAnswer:")
    assert "abgerufener Kontext gekürzt" in prompt and len(prompt) < 9000
    assert adapter._sent_chars <= (4000 - 1500) * adapter._chars_per_token


def test_evidence_is_cut_only_after_history_and_context_are_gone():
    adapter = _budget_adapter(3000, prompt=_prompt_with_context("K" * 2000, "Frage?"))
    adapter.add_tool_results([ToolCall("bootstrap-0", "answer_context", {})], ["B" * 9000], None)

    adapter._fit_messages()

    result = adapter.messages[-1]["content"]
    assert result.startswith("BBB") and "Werkzeugergebnis gekürzt" in result
    assert "Question: Frage?" in adapter.messages[1]["content"]


def _rejected(prompt_tokens: int, context_tokens: int):
    body = json.dumps(
        {
            "error": json.dumps(
                {
                    "error": {
                        "code": 400,
                        "message": f"request ({prompt_tokens} tokens) exceeds the available context size",
                        "type": "exceed_context_size_error",
                        "n_prompt_tokens": prompt_tokens,
                        "n_ctx": context_tokens,
                    }
                }
            )
        }
    )

    async def aread():
        return body.encode()

    return SimpleNamespace(is_success=False, status_code=400, text=body, aread=aread)


def _serve_responses(monkeypatch, responses: list) -> list[dict]:
    requests: list[dict] = []

    @contextlib.asynccontextmanager
    async def mock_admitted_stream(_client, _url, **kwargs):
        requests.append(json.loads(json.dumps(kwargs["json"])))
        reply = responses[len(requests) - 1]
        if not isinstance(reply, list):
            yield reply
            return
        response = SimpleNamespace(is_success=True)

        async def aiter_lines():
            for line in reply:
                yield line

        response.aiter_lines = aiter_lines
        yield response

    monkeypatch.setattr("services.agent_providers.admitted_stream", mock_admitted_stream)
    return requests


@pytest.mark.asyncio
async def test_a_rejected_oversized_request_is_cut_with_the_server_token_count_and_retried(
    monkeypatch,
):
    requests = _serve_responses(
        monkeypatch, [_rejected(9000, 4096), [_ollama_line(text="Antwort")]]
    )
    history = [{"role": "user", "content": "alt " * 2500}, {"role": "assistant", "content": "ok"}]

    # Das Profil nennt ein größeres Fenster, als der Server tatsächlich hat.
    events = await _run("ollama", context_length=32768, chat_history=history)

    assert requests[0]["truncate"] is False
    assert len(requests[0]["messages"]) == 4 and len(requests[1]["messages"]) < 4
    assert requests[1]["messages"][-1]["content"] == "Frage"
    assert events[-1]["content"] == "Antwort"


@pytest.mark.asyncio
async def test_a_request_that_cannot_be_cut_any_further_fails_with_a_clear_error(monkeypatch):
    from core.inference_errors import ContextWindowExceeded

    _serve_responses(
        monkeypatch, [_rejected(9000, 512), _rejected(9000, 512), _rejected(9000, 512)]
    )

    with pytest.raises(ContextWindowExceeded, match="passt nicht in das Kontextfenster"):
        await _run("ollama", context_length=512)


def test_context_overflow_is_recognised_for_llama_cpp_and_vllm_wording():
    from core.inference_errors import context_overflow

    llama = context_overflow(
        '{"error":{"type":"exceed_context_size_error","n_prompt_tokens":7258,"n_ctx":2048}}'
    )
    assert (llama.prompt_tokens, llama.context_tokens) == (7258, 2048)
    vllm = context_overflow(
        "This model's maximum context length is 8192 tokens. However, you requested 9000 tokens "
        "(8000 in the messages, 1000 in the completion)."
    )
    assert (vllm.prompt_tokens, vllm.context_tokens) == (8000, 8192)
    assert context_overflow("model not found") is None


def test_special_tools_are_offered_only_when_the_question_sounds_like_them():
    from services.agent_tool_defs import select_tools_for_question

    tools = local_tool_definitions(True, [{"chunk_id": 1}], 1)

    def offered(question: str) -> set[str]:
        return {tool["name"] for tool in select_tools_for_question(tools, question)}

    core = offered("Was macht das Programm CBACT04C?")
    assert core == {
        "list_repo_files",
        "view_repo_file",
        "search_repo_code",
        "answer_context",
        "search_knowledge",
        "get_repo_entities",
        "trace_call_flow",
    }
    assert "offer_code_walkthrough" in offered("Gib mir eine Tour durch den Code")
    assert "inspect_change_impact" in offered("Was betrifft eine Änderung an COPAUA0C?")
    assert "view_commit_diff" in offered("Was hat sich zwischen den Commits geändert?")
    assert "get_source_status" in offered("Welche Dateien wurden nur teilweise analysiert?")
    assert "show_graph_neighborhood" in offered("Zeige die Abhängigkeiten als Graph")


def test_system_prompt_carries_only_the_instructions_of_offered_tools():
    from services.agent_prompt import build_system_prompt

    core = build_system_prompt(None, {"answer_context", "view_repo_file", "trace_call_flow"})
    assert "`trace_call_flow`" in core and "pfad/zur/datei.ext:zeile" in core
    for absent in ("offer_code_walkthrough", "inspect_change_package", "view_commit_diff"):
        assert absent not in core
    everything = build_system_prompt(None)
    assert "offer_code_walkthrough" in everything and len(core) < len(everything) * 0.6


def test_base_load_of_an_ordinary_question_leaves_most_of_an_8k_window_free():
    """Systemtext und Werkzeugschemata belegten zuvor rund 5.000 der 8.192 Tokens."""
    from services.agent_prompt import build_system_prompt
    from services.agent_tool_defs import select_tools_for_question

    tools = select_tools_for_question(
        local_tool_definitions(True, [{"chunk_id": 1}], 1), "Was macht das Programm CBACT04C?"
    )
    prompt = build_system_prompt(None, {tool["name"] for tool in tools})

    assert len(prompt) + len(json.dumps(tools, ensure_ascii=False)) < 11000


@pytest.mark.asyncio
async def test_standard_chat_drops_history_before_the_question_and_disables_silent_truncation(
    monkeypatch,
):
    captured = {}

    @contextlib.asynccontextmanager
    async def mock_admitted_stream(_client, _url, **kwargs):
        captured.update(kwargs["json"])
        response = SimpleNamespace(is_success=True)

        async def aiter_lines():
            yield json.dumps({"message": {"content": "Hi"}, "done": True})

        response.aiter_lines = aiter_lines
        yield response

    monkeypatch.setattr("services.chat_service.admitted_stream", mock_admitted_stream)
    history = [SimpleNamespace(role="user", content="alt " * 3000)]
    [
        event
        async for event in stream_standard_rag_events(
            provider="ollama",
            model="test-model",
            api_key=None,
            base_url="http://ollama:11434",
            temperature=None,
            system_prompt="System",
            history=history,
            prompt="Frage",
            context_length=2048,
        )
    ]

    assert captured["truncate"] is False
    assert [m["content"] for m in captured["messages"]] == ["System", "Frage"]


@pytest.mark.asyncio
async def test_standard_chat_reports_an_oversized_request_instead_of_answering_blind(monkeypatch):
    @contextlib.asynccontextmanager
    async def mock_admitted_stream(_client, _url, **_kwargs):
        yield _rejected(9000, 2048)

    monkeypatch.setattr("services.chat_service.admitted_stream", mock_admitted_stream)
    events = [
        event
        async for event in stream_standard_rag_events(
            provider="ollama",
            model="test-model",
            api_key=None,
            base_url="http://ollama:11434",
            temperature=None,
            system_prompt="System",
            history=[],
            prompt="Frage",
        )
    ]

    assert events[-1]["type"] == "error"
    assert "9000 Tokens bei einem Fenster von 2048" in events[-1]["error"]
