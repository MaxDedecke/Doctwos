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
    payloads = []

    async def fake_post(url, json, timeout, headers=None):
        texts = json["input"]
        calls.append(list(texts))
        payloads.append(json)
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
    assert all(payload["dimensions"] == ollama_client.EMBEDDING_DIMENSION for payload in payloads)
    assert all(
        payload["options"] == {"num_ctx": ollama_client.OLLAMA_NUM_CTX} for payload in payloads
    )


@pytest.mark.anyio
async def test_get_embeddings_batch_uses_configured_timeout(monkeypatch):
    monkeypatch.setattr(ollama_client, "EMBED_BATCH_TIMEOUT", 42.0)

    seen_timeouts = []

    async def fake_post(url, json, timeout, headers=None):
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
async def test_get_embeddings_batch_supports_openai_compatible_remote_endpoint(monkeypatch):
    captured = {}

    async def fake_post(url, json, timeout, headers=None):
        captured.update(url=url, payload=json, headers=headers)
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(
            return_value={"data": [{"embedding": [0.1]}, {"embedding": [0.2]}]}
        )
        return response

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=fake_post)
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)
    monkeypatch.setattr(ollama_client, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(ollama_client, "EMBEDDING_BASE_URL", "https://ai.example/v1")
    monkeypatch.setattr(ollama_client, "EMBEDDING_API_KEY", "secret")

    assert await ollama_client.get_embeddings_batch(["a", "b"], model="bge-m3") == [[0.1], [0.2]]
    assert captured == {
        "url": "https://ai.example/v1/embeddings",
        "payload": {"model": "bge-m3", "input": ["a", "b"]},
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer secret"},
    }


@pytest.mark.anyio
async def test_get_embeddings_batch_uses_active_profile_subpath(monkeypatch):
    captured = {}

    async def fake_post(url, json, timeout, headers=None):
        captured.update(url=url, headers=headers)
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"embeddings": [[0.1]]})
        return response

    monkeypatch.setattr(
        ollama_client,
        "_load_server_settings",
        lambda: {
            "embedding_provider": "ollama",
            "embedding_model": "remote-embed",
            "embedding_base_url": "https://inference.internal:8443/ollama",
            "embedding_api_key": "secret",
            "embedding_path": "/tenant/api/embed",
            "embedding_dimension": 1024,
            "embedding_context_length": 4096,
        },
    )
    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=fake_post)
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    assert await ollama_client.get_embeddings_batch(["a"]) == [[0.1]]
    assert captured == {
        "url": "https://inference.internal:8443/ollama/tenant/api/embed",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer secret"},
    }


@pytest.mark.anyio
async def test_managed_embedding_endpoint_does_not_pull_models(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)
    monkeypatch.setattr(ollama_client, "EMBEDDING_AUTO_PULL", False)

    await ollama_client.ensure_model_pulled("bge-m3")

    fake_client.post.assert_not_called()


@pytest.mark.anyio
async def test_get_embedding_uses_openai_compatible_adapter(monkeypatch):
    fake_client = MagicMock()
    fake_client.post = AsyncMock()
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)
    monkeypatch.setattr(ollama_client, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(
        ollama_client,
        "get_embeddings_batch",
        AsyncMock(return_value=[[0.1, 0.2]]),
    )

    assert await ollama_client.get_embedding("chunk", model="remote-embed") == [0.1, 0.2]
    ollama_client.get_embeddings_batch.assert_awaited_once_with(["chunk"], model="remote-embed")


@pytest.mark.anyio
async def test_get_embeddings_batch_empty_returns_empty():
    assert await ollama_client.get_embeddings_batch([], model="bge-m3") == []


def _fake_ps_client(models_response, post_raises=None):
    fake_client = MagicMock()

    async def fake_post(url, json, timeout, headers=None):
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


@pytest.mark.anyio
async def test_get_chat_json_sets_explicit_num_ctx(monkeypatch):
    """O-168: ohne num_ctx faellt Ollama auf sein kleines, stillschweigend
    kuerzendes Default-Kontextfenster zurueck -- fuer den Compliance-Checker
    hiesse das, dass Regelwerk oder Elementinhalt unbemerkt aus dem Prompt
    fallen koennen."""
    monkeypatch.setattr(ollama_client, "OLLAMA_NUM_CTX", 12345)
    captured = {}

    async def fake_post(url, json, timeout, headers=None):
        captured.update(url=url, payload=json)
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"message": {"content": '{"ok": true}'}})
        return response

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=fake_post)
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    result = await ollama_client.get_chat_json("Frage", model="test-model")

    assert result == {"ok": True}
    assert captured["payload"]["options"] == {"num_ctx": 12345}
