from unittest.mock import AsyncMock, MagicMock

import pytest

import ollama_client


@pytest.mark.anyio
async def test_get_embeddings_batch_splits_into_sub_batches(monkeypatch):
    """E-8: ein Dokument mit mehr Chunks als EMBED_BATCH_MAX_CHUNKS darf nicht
    in einem einzigen Request landen — sonst droht bei CPU-only-Embedding
    wieder der 120s-Timeout aus dem AP-9-Lasttest."""
    monkeypatch.setattr(ollama_client, "EMBED_BATCH_MAX_CHUNKS", 2)
    monkeypatch.setattr(ollama_client, "EMBEDDING_DIMENSION", 1)

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
        payload["options"] == {"num_ctx": ollama_client.EMBEDDING_CONTEXT_LENGTH}
        for payload in payloads
    )


@pytest.mark.anyio
async def test_get_embeddings_batch_uses_configured_timeout(monkeypatch):
    monkeypatch.setattr(ollama_client, "EMBED_BATCH_TIMEOUT", 42.0)
    monkeypatch.setattr(ollama_client, "EMBEDDING_DIMENSION", 1)

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
    monkeypatch.setattr(ollama_client, "EMBEDDING_DIMENSION", 1)

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
            "embedding_dimension": 1,
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


@pytest.mark.anyio
async def test_qwen_embedding_contract_uses_token_context_and_1024_dimensions(monkeypatch):
    payloads = []

    async def fake_post(url, json, timeout, headers=None):
        payloads.append(json)
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"embeddings": [[0.0] * 1024]})
        return response

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=fake_post)
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)
    monkeypatch.setattr(ollama_client, "EMBEDDING_DIMENSION", 1024)
    monkeypatch.setattr(ollama_client, "EMBEDDING_CONTEXT_LENGTH", 8100)

    result = await ollama_client.get_embeddings_batch(
        ["Deutsche Fachfrage zu app.Main#run(int)"], model="qwen3-embedding:4b"
    )

    assert len(result[0]) == 1024
    assert payloads == [
        {
            "model": "qwen3-embedding:4b",
            "input": ["Deutsche Fachfrage zu app.Main#run(int)"],
            "dimensions": 1024,
            "options": {"num_ctx": 8100},
        }
    ]


@pytest.mark.anyio
async def test_embedding_contract_rejects_wrong_dimension_or_count(monkeypatch):
    monkeypatch.setattr(ollama_client, "EMBEDDING_DIMENSION", 2)

    async def fake_post(url, json, timeout, headers=None):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"embeddings": [[0.0]]})
        return response

    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=fake_post)
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    with pytest.raises(ValueError, match="falsche Dimension"):
        await ollama_client.get_embeddings_batch(["x"])


@pytest.mark.anyio
async def test_embedding_contract_rejects_input_over_token_budget(monkeypatch):
    monkeypatch.setattr(ollama_client, "EMBEDDING_CONTEXT_LENGTH", 10)
    fake_client = MagicMock()
    fake_client.post = AsyncMock()
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_client)

    with pytest.raises(ValueError, match="Tokenbudget"):
        await ollama_client.get_embeddings_batch(["12345678901"])

    fake_client.post.assert_not_awaited()


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
async def test_is_gpu_accelerated_matches_implicit_latest_tag(monkeypatch):
    fake_client = _fake_ps_client(
        {"models": [{"model": "bge-m3:latest", "size_vram": 664000265}]}
    )
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


def test_requested_model_equal_to_the_active_profile_model_uses_the_profile(monkeypatch):
    """Link-Läufe geben den Profilnamen weiter; er darf nicht an Ollama gehen (404)."""
    import ollama_client as oc

    monkeypatch.setenv("LLM_MODEL", "qwen3:8b")
    monkeypatch.setattr(oc, "_load_server_settings", lambda: {
        "llm_model": "gpt-6-luna", "llm_base_url": "https://api.openai.com/v1", "llm_api_key": "k",
        "protocol": "openai_responses", "llm_path": "/responses", "llm_context_length": 8192,
    })
    profile = oc._effective_llm_settings("gpt-6-luna")
    assert (profile["protocol"], profile["model"], profile["base_url"]) == (
        "openai_responses", "gpt-6-luna", "https://api.openai.com/v1",
    )
    # Ein fremdes Modell ohne Profilbezug bleibt eine direkte Ollama-Anfrage.
    other = oc._effective_llm_settings("some-other-model")
    assert (other["protocol"], other["model"]) == ("ollama", "some-other-model")


@pytest.mark.anyio
async def test_disabled_active_profile_is_not_overridden_by_the_env_model(monkeypatch):
    """Profil „Lokales Ollama“ (LLM disabled) + Worker-Env LLM_MODEL=qwen3:8b: kein Aufruf."""
    import ollama_client as oc

    monkeypatch.setenv("LLM_MODEL", "qwen3:8b")
    monkeypatch.setattr(oc, "_load_server_settings", lambda: {
        "llm_model": "disabled", "llm_base_url": "http://ollama:11434", "llm_api_key": "",
        "protocol": "ollama", "llm_path": None, "llm_context_length": 8192,
    })
    called = []
    monkeypatch.setattr(oc, "admitted_post", lambda *a, **k: called.append(1))
    with pytest.raises(RuntimeError, match="deaktiviert"):
        await oc.get_chat_json("x", "qwen3:8b")
    assert not called


def test_missing_embedding_profile_gives_a_clear_error_instead_of_a_connection_to_ollama(monkeypatch):
    # Standard-Stack ohne LLM-Container: DB erreichbar, aber weder Profil noch Endpunkt in der Umgebung.
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setattr(ollama_client, "_load_server_settings", lambda: {"embedding_base_url": None})
    with pytest.raises(ollama_client.EmbeddingNotConfigured, match="Kein Embedding-Profil"):
        ollama_client._effective_embedding_settings()
    # Chunking braucht nur die Obergrenze und darf daran nicht scheitern.
    assert ollama_client.get_embedding_input_budget() == ollama_client.EMBEDDING_CONTEXT_LENGTH


def test_embedding_endpoint_from_the_worker_environment_still_counts_as_configured(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://inference.internal:11434")
    monkeypatch.setattr(ollama_client, "_load_server_settings", lambda: {
        "embedding_provider": "ollama", "embedding_base_url": None, "embedding_api_key": "", "embedding_path": None,
        "embedding_model": "bge-m3", "embedding_dimension": 1024, "embedding_context_length": 8192,
    })
    assert ollama_client._effective_embedding_settings()["model"] == "bge-m3"
