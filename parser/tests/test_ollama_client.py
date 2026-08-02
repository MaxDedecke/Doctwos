from unittest.mock import AsyncMock, MagicMock

import pytest

import ollama_client


@pytest.mark.anyio
async def test_get_embeddings_batch_splits_into_sub_batches(monkeypatch):
    """E-8: ein Dokument mit mehr Chunks als EMBED_BATCH_MAX_CHUNKS darf nicht
    in einem einzigen Request landen — sonst droht bei CPU-only-Embedding
    wieder der 120s-Timeout aus dem AP-9-Lasttest."""
    monkeypatch.setattr(ollama_client, "EMBED_BATCH_MAX_CHUNKS", 2)

    calls = []

    async def fake_post(url, json, timeout):
        texts = json["input"]
        calls.append(list(texts))
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"embeddings": [[float(len(t))] for t in texts]})
        return response

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=fake_post)
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    texts = ["a", "bb", "ccc", "dddd", "e"]
    embeddings = await ollama_client.get_embeddings_batch(texts, model="bge-m3")

    assert len(calls) == 3
    assert [len(c) for c in calls] == [2, 2, 1]
    assert embeddings == [[1.0], [2.0], [3.0], [4.0], [1.0]]


@pytest.mark.anyio
async def test_get_embeddings_batch_uses_configured_timeout(monkeypatch):
    monkeypatch.setattr(ollama_client, "EMBED_BATCH_TIMEOUT", 42.0)

    seen_timeouts = []

    async def fake_post(url, json, timeout):
        seen_timeouts.append(timeout)
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"embeddings": [[0.0] for _ in json["input"]]})
        return response

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=fake_post)
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    await ollama_client.get_embeddings_batch(["x"], model="bge-m3")

    assert seen_timeouts == [42.0]


@pytest.mark.anyio
async def test_get_embeddings_batch_empty_returns_empty():
    assert await ollama_client.get_embeddings_batch([], model="bge-m3") == []
