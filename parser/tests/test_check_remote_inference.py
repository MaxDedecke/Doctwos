import importlib.util
import json
from pathlib import Path
import httpx
import pytest


def probe():
    path = Path(__file__).resolve().parents[2] / "scripts/check_remote_inference.py"
    spec = importlib.util.spec_from_file_location("check_remote_inference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("provider", ["ollama", "vllm"])
def test_remote_probe_exercises_chat_and_separate_embeddings(provider, monkeypatch):
    for key in ("LLM_API_KEY", "OLLAMA_API_KEY", "EMBEDDING_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    paths = []

    def handler(request):
        assert "Authorization" not in request.headers
        paths.append((request.url.host, request.url.path))
        if request.url.host == "chat":
            if b'"tools"' in request.content:
                return tool_stream()
            return httpx.Response(
                200,
                json={"message": {"content": "OK"}}
                if provider == "ollama"
                else {"choices": [{"message": {"content": "OK"}}]},
            )
        return httpx.Response(200, json={"data": [{"embedding": [0.01] * 1024}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert probe().check(
            client,
            chat_url="http://chat/v1",
            chat_model="pilot",
            chat_provider=provider,
            embedding_url="http://embed/v1",
            embedding_model="embed",
            embedding_provider="openai",
        )
    chat = (
        [("chat", "/v1/api/chat")]
        if provider == "ollama"
        else [("chat", "/v1/chat/completions")] * 2
    )
    assert paths == [*chat, ("embed", "/v1/embeddings")]


def tool_stream(name="doctus_profile_probe"):
    delta = {"tool_calls": [{"index": 0, "function": {"name": name, "arguments": "{}"}}]}
    body = f"data: {json.dumps({'choices': [{'delta': delta}]})}\n\ndata: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


@pytest.mark.parametrize(
    "answer, message",
    [
        (lambda: tool_stream("other"), "tool call"),
        (lambda: httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]}), "events"),
        (lambda: httpx.Response(400, json={"error": "unknown field stream_options"}), "HTTP 400"),
    ],
)
def test_remote_probe_requires_the_streamed_tool_call_of_the_chat_agent(answer, message):
    def handler(request):
        if request.url.host == "chat":
            if b'"tools"' in request.content:
                body = json.loads(request.content)
                assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
                return answer()
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        return httpx.Response(200, json={"data": [{"embedding": [0.01] * 1024}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match=message):
            probe().check(
                client,
                chat_url="http://chat/v1",
                chat_model="pilot",
                chat_provider="vllm",
                embedding_url="http://embed/v1",
                embedding_model="embed",
                embedding_provider="openai",
            )


def test_remote_probe_rejects_wrong_vector_dimensions():
    def handler(request):
        if request.url.host == "chat":
            if b'"tools"' in request.content:
                return tool_stream()
            return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        return httpx.Response(200, json={"data": [{"embedding": [0] * 768}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="1024"):
            probe().check(
                client,
                chat_url="http://chat/v1",
                chat_model="pilot",
                chat_provider="vllm",
                embedding_url="http://embed/v1",
                embedding_model="embed",
                embedding_provider="openai",
            )
