from unittest.mock import MagicMock

import pytest

import core.config as cfg
from services.ollama_client import embed_text


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _AsyncClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, *_args, **_kwargs):
        return self.response


@pytest.mark.anyio
async def test_qwen_embedding_request_uses_8100_context_and_validates_1024(monkeypatch):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"embeddings": [[0.0] * 1024]})
    captured = {}

    async def fake_post(self, url, json, **kwargs):
        captured.update(url=url, payload=json)
        return response

    monkeypatch.setattr("services.ollama_client.httpx.AsyncClient", lambda **_: _AsyncClient(response))
    monkeypatch.setattr(_AsyncClient, "post", fake_post)
    monkeypatch.setattr(cfg, "EMBEDDING_DIMENSION", 1024)
    monkeypatch.setattr(cfg, "EMBEDDING_CONTEXT_LENGTH", 8100)

    embedding = await embed_text("Java app.Main#run(int)", is_query=True, model="qwen3-embedding:4b")

    assert len(embedding) == 1024
    assert captured["payload"] == {
        "model": "qwen3-embedding:4b",
        "input": "Java app.Main#run(int)",
        "dimensions": 1024,
        "options": {"num_ctx": 8100},
    }


@pytest.mark.anyio
async def test_backend_embedding_rejects_wrong_dimension(monkeypatch):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value={"embeddings": [[0.0]]})
    monkeypatch.setattr("services.ollama_client.httpx.AsyncClient", lambda **_: _AsyncClient(response))
    monkeypatch.setattr(cfg, "EMBEDDING_DIMENSION", 2)

    with pytest.raises(ValueError, match="falsche Dimension"):
        await embed_text("x", model="qwen3-embedding:4b")


@pytest.mark.anyio
async def test_backend_embedding_rejects_input_over_token_budget(monkeypatch):
    monkeypatch.setattr(cfg, "EMBEDDING_CONTEXT_LENGTH", 10)

    with pytest.raises(ValueError, match="Tokenbudget"):
        await embed_text("12345678901", model="qwen3-embedding:4b")
