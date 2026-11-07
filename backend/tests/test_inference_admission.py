import pytest

from doctus_models import inference_admission as admission


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_endpoint_pool_is_shared_by_paths_on_the_same_server():
    assert admission._pool_id("https://inference.example/api/chat") == admission._pool_id(
        "https://inference.example:443/v1/embeddings"
    )
    assert admission._pool_id("https://other.example/api/chat") != admission._pool_id(
        "https://inference.example/api/chat"
    )


def test_chat_and_batch_each_keep_one_slot_free_for_the_other_class(monkeypatch):
    monkeypatch.setattr(admission, "MAX_CONCURRENCY", 4)
    monkeypatch.setattr(admission, "CHAT_RESERVE", 1)
    monkeypatch.setattr(admission, "BATCH_RESERVE", 1)

    assert admission._class_settings("chat") == (1, 3)
    assert admission._class_settings("batch") == (2, 3)


@pytest.mark.anyio
async def test_inference_slot_releases_lease_when_request_fails(monkeypatch):
    calls = []

    async def fake_eval(script, keys, *args):
        calls.append((script, keys, args))
        if script == admission._ACQUIRE_SCRIPT:
            return [1, 1, 1, 0]
        return 0

    monkeypatch.setattr(admission, "_eval", fake_eval)
    monkeypatch.setattr(admission, "_redis_unavailable_until", 0.0)
    monkeypatch.setattr(admission, "MAX_CONCURRENCY", 4)
    monkeypatch.setattr(admission, "CHAT_RESERVE", 1)
    monkeypatch.setattr(admission, "BATCH_RESERVE", 1)

    with pytest.raises(RuntimeError, match="request failed"):
        async with admission.inference_slot("chat", "https://model.example/api/chat"):
            raise RuntimeError("request failed")

    acquire = next(call for call in calls if call[0] == admission._ACQUIRE_SCRIPT)
    assert acquire[2][2:5] == (4, 3, 1)
    assert any(call[0] == admission._RELEASE_SCRIPT for call in calls)


@pytest.mark.anyio
async def test_saturated_endpoint_times_out_and_records_wait_metric(monkeypatch):
    calls = []

    async def fake_eval(script, keys, *args):
        calls.append((script, keys, args))
        if script == admission._ACQUIRE_SCRIPT:
            return [0, 4, 3, 1]
        return 1

    monkeypatch.setattr(admission, "_eval", fake_eval)
    monkeypatch.setattr(admission, "_redis_unavailable_until", 0.0)
    monkeypatch.setattr(admission, "POLL_SECONDS", 0.01)

    with pytest.raises(admission.InferenceAdmissionTimeout):
        async with admission.inference_slot(
            "chat", "https://model.example/api/chat", wait_timeout_seconds=0
        ):
            pytest.fail("a saturated endpoint must not admit the request")

    assert any(call[0] == admission._WAIT_METRIC_SCRIPT for call in calls)


@pytest.mark.anyio
async def test_batch_and_chat_use_the_limit_a_profile_published_for_the_endpoint(monkeypatch):
    """Parser (batch) und API (chat) teilen dieses Modul; beide müssen das Profil-Limit sehen."""
    calls = []

    async def fake_eval(script, keys, *args):
        calls.append((script, args))
        if script == admission._GET_LIMIT_SCRIPT:
            return "8"
        if script == admission._ACQUIRE_SCRIPT:
            return [1, 1, 0, 1]
        return 1

    monkeypatch.setattr(admission, "_eval", fake_eval)
    monkeypatch.setattr(admission, "_redis_unavailable_until", 0.0)
    monkeypatch.setattr(admission, "_limit_cache", {})
    monkeypatch.setattr(admission, "MAX_CONCURRENCY", 4)
    monkeypatch.setattr(admission, "CHAT_RESERVE", 1)
    monkeypatch.setattr(admission, "BATCH_RESERVE", 1)

    async with admission.inference_slot("batch", "http://vllm.local:8000/v1/embeddings"):
        pass

    acquire = next(args for script, args in calls if script == admission._ACQUIRE_SCRIPT)
    assert acquire[2:4] == (8, 7)  # max_total, Klassenlimit Batch
