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


def _fake_ps_client(models_response, post_raises=None):
    fake_client = MagicMock()

    async def fake_post(url, json, timeout):
        if post_raises:
            raise post_raises
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"embeddings": [[0.0]]})
        return response

    async def fake_get(url, timeout):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value=models_response)
        return response

    fake_client.post = AsyncMock(side_effect=fake_post)
    fake_client.get = AsyncMock(side_effect=fake_get)
    return fake_client


@pytest.mark.anyio
async def test_is_gpu_accelerated_true_when_size_vram_positive(monkeypatch):
    """O-071: size_vram > 0 heißt (teil-)GPU-beschleunigt -- volle
    EMBED_CONCURRENCY bleibt sinnvoll."""
    fake_client = _fake_ps_client({"models": [{"model": "bge-m3", "size_vram": 12345}]})
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    assert await ollama_client.is_gpu_accelerated("bge-m3") is True


@pytest.mark.anyio
async def test_is_gpu_accelerated_false_when_size_vram_zero(monkeypatch):
    """size_vram == 0 heißt CPU-only -- Aufrufer muss drosseln (O-071)."""
    fake_client = _fake_ps_client({"models": [{"model": "bge-m3", "size_vram": 0}]})
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    assert await ollama_client.is_gpu_accelerated("bge-m3") is False


@pytest.mark.anyio
async def test_is_gpu_accelerated_false_when_model_not_listed(monkeypatch):
    """Modell nicht in /api/ps (z. B. gerade wieder entladen) -- konservativer
    CPU-only-Fallback statt Annahme von GPU-Beschleunigung."""
    fake_client = _fake_ps_client({"models": []})
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    assert await ollama_client.is_gpu_accelerated("bge-m3") is False


@pytest.mark.anyio
async def test_is_gpu_accelerated_false_when_ollama_unreachable(monkeypatch):
    """/api/ps nicht erreichbar -- konservativer CPU-only-Fallback statt Absturz."""
    import httpx

    fake_client = _fake_ps_client({}, post_raises=httpx.ConnectError("no route"))
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    assert await ollama_client.is_gpu_accelerated("bge-m3") is False
