import importlib.util
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
    assert paths == [
        ("chat", "/v1/api/chat" if provider == "ollama" else "/v1/chat/completions"),
        ("embed", "/v1/embeddings"),
    ]


def test_remote_probe_rejects_wrong_vector_dimensions():
    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{}]}
            if request.url.host == "chat"
            else {"data": [{"embedding": [0] * 768}]},
        )

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
