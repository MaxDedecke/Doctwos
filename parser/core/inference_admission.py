"""Redis-coordinated admission control for shared model endpoints.

Both the API and parser worker carry this small implementation because their
Docker build contexts are separate. Keep the copies identical. Batch work and
interactive chat reserve capacity from each other so neither can consume all
slots on a shared endpoint.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator
from urllib.parse import urlsplit

import redis

logger = logging.getLogger(__name__)

admission_wait_tracker: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar(
    "admission_wait_tracker", default=None
)


@contextmanager
def track_admission_wait() -> Iterator[list[int]]:
    """Context manager to record admission wait times (in ms) for inference requests."""
    times: list[int] = []
    token = admission_wait_tracker.set(times)
    try:
        yield times
    finally:
        admission_wait_tracker.reset(token)


REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MAX_CONCURRENCY = max(2, int(os.getenv("INFERENCE_MAX_CONCURRENCY", "4")))
CHAT_RESERVE = min(
    MAX_CONCURRENCY - 1,
    max(1, int(os.getenv("INFERENCE_CHAT_RESERVE", "1"))),
)
BATCH_RESERVE = min(
    MAX_CONCURRENCY - 1,
    max(1, int(os.getenv("INFERENCE_BATCH_RESERVE", "1"))),
)
LEASE_MS = max(30_000, int(os.getenv("INFERENCE_LEASE_SECONDS", "60")) * 1000)
RENEW_SECONDS = max(5.0, min(20.0, LEASE_MS / 3000))
POLL_SECONDS = max(0.05, float(os.getenv("INFERENCE_POLL_SECONDS", "0.25")))
CHAT_WAIT_SECONDS = max(0.0, float(os.getenv("INFERENCE_CHAT_WAIT_SECONDS", "30")))
BATCH_WAIT_SECONDS = max(0.0, float(os.getenv("INFERENCE_BATCH_WAIT_SECONDS", "900")))
METRICS_LOG_INTERVAL = max(10.0, float(os.getenv("INFERENCE_METRICS_LOG_INTERVAL", "60")))

_redis_client: redis.Redis | None = None
_last_metrics_log: dict[tuple[str, str], float] = {}
_redis_warning_logged = False
_redis_unavailable_until = 0.0

_ACQUIRE_SCRIPT = """
local time_parts = redis.call('TIME')
local now_ms = (tonumber(time_parts[1]) * 1000) + math.floor(tonumber(time_parts[2]) / 1000)
local lease_ms = tonumber(ARGV[2])
local max_total = tonumber(ARGV[3])
local class_limit = tonumber(ARGV[4])
local class_index = tonumber(ARGV[5])
local token = ARGV[1]
local metrics_key = KEYS[3]

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now_ms)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now_ms)
local active_chat = redis.call('ZCARD', KEYS[1])
local active_batch = redis.call('ZCARD', KEYS[2])
local active_total = active_chat + active_batch
local active_class = class_index == 1 and active_chat or active_batch

if active_total < max_total and active_class < class_limit then
  local active_key = KEYS[class_index]
  redis.call('ZADD', active_key, now_ms + lease_ms, token)
  redis.call('PEXPIRE', active_key, lease_ms * 3)
  active_total = active_total + 1
  active_class = active_class + 1
  local kind = class_index == 1 and 'chat' or 'batch'
  redis.call('HINCRBY', metrics_key, 'requests:' .. kind, 1)
  if tonumber(ARGV[6]) > 0 then
    local waited_ms = tonumber(ARGV[6])
    redis.call('HINCRBY', metrics_key, 'throttled:' .. kind, 1)
    redis.call('HINCRBY', metrics_key, 'wait_ms_total:' .. kind, waited_ms)
    local max_field = 'wait_ms_max:' .. kind
    local old_max = tonumber(redis.call('HGET', metrics_key, max_field) or '0')
    if waited_ms > old_max then redis.call('HSET', metrics_key, max_field, waited_ms) end
  end
  redis.call('HSET', metrics_key,
    'active_slots', active_total,
    'utilization_percent', math.floor((active_total * 100) / max_total),
    'max_concurrency', max_total)
  redis.call('EXPIRE', metrics_key, 2592000)
  return {
    1,
    active_total,
    active_chat + (class_index == 1 and 1 or 0),
    active_batch + (class_index == 2 and 1 or 0)
  }
end

redis.call('HSET', metrics_key,
  'active_slots', active_total,
  'utilization_percent', math.floor((active_total * 100) / max_total),
  'max_concurrency', max_total)
redis.call('EXPIRE', metrics_key, 2592000)
return {0, active_total, active_chat, active_batch}
"""

_RENEW_SCRIPT = """
local time_parts = redis.call('TIME')
local now_ms = (tonumber(time_parts[1]) * 1000) + math.floor(tonumber(time_parts[2]) / 1000)
local score = redis.call('ZSCORE', KEYS[1], ARGV[1])
if not score then return 0 end
redis.call('ZADD', KEYS[1], 'XX', now_ms + tonumber(ARGV[2]), ARGV[1])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]) * 3)
return 1
"""

_RELEASE_SCRIPT = """
local time_parts = redis.call('TIME')
local now_ms = (tonumber(time_parts[1]) * 1000) + math.floor(tonumber(time_parts[2]) / 1000)
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now_ms)
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now_ms)
local chat_count = redis.call('ZCARD', KEYS[2])
local batch_count = redis.call('ZCARD', KEYS[3])
local active_total = chat_count + batch_count
redis.call('HSET', KEYS[4],
  'active_slots', active_total,
  'utilization_percent', math.floor((active_total * 100) / tonumber(ARGV[2])),
  'max_concurrency', tonumber(ARGV[2]))
if redis.call('ZCARD', KEYS[1]) == 0 then redis.call('DEL', KEYS[1]) end
return active_total
"""

_WAIT_METRIC_SCRIPT = """
local kind = ARGV[1]
local elapsed_ms = tonumber(ARGV[2])
redis.call('HINCRBY', KEYS[1], 'timeouts:' .. kind, 1)
redis.call('HINCRBY', KEYS[1], 'wait_ms_total:' .. kind, elapsed_ms)
local max_field = 'wait_ms_max:' .. kind
local old_max = tonumber(redis.call('HGET', KEYS[1], max_field) or '0')
if elapsed_ms > old_max then redis.call('HSET', KEYS[1], max_field, elapsed_ms) end
redis.call('EXPIRE', KEYS[1], 2592000)
return 1
"""


class InferenceAdmissionTimeout(TimeoutError):
    """The endpoint stayed at its configured capacity for too long."""


def _client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            REDIS_URL,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            health_check_interval=30,
            decode_responses=True,
        )
    return _redis_client


def _pool_id(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    host = (parsed.hostname or endpoint).casefold()
    port = parsed.port
    scheme = parsed.scheme.casefold()
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    origin = f"{scheme}://{host}:{port or ''}"
    return hashlib.sha256(origin.encode("utf-8")).hexdigest()[:20]


def _keys(pool_id: str) -> tuple[str, str, str]:
    prefix = f"doctus:inference:v1:{{{pool_id}}}"
    return f"{prefix}:active:chat", f"{prefix}:active:batch", f"{prefix}:metrics"


async def _eval(script: str, keys: tuple[str, ...], *args: Any) -> Any:
    return await asyncio.to_thread(_client().eval, script, len(keys), *keys, *args)


def _class_settings(kind: str) -> tuple[int, int]:
    if kind == "chat":
        return 1, MAX_CONCURRENCY - BATCH_RESERVE
    if kind == "batch":
        return 2, MAX_CONCURRENCY - CHAT_RESERVE
    raise ValueError(f"Unbekannte Inference-Klasse: {kind!r}")


async def _renew(key: str, token: str) -> None:
    while True:
        await asyncio.sleep(RENEW_SECONDS)
        try:
            alive = await _eval(_RENEW_SCRIPT, (key,), token, LEASE_MS)
            if not alive:
                return
        except Exception:
            logger.warning("Inference admission lease renewal failed", exc_info=True)


def _log_metrics(pool_id: str, kind: str, active: int, waited_ms: int) -> None:
    now = time.monotonic()
    key = (pool_id, kind)
    previous = _last_metrics_log.get(key, 0.0)
    if waited_ms or now - previous >= METRICS_LOG_INTERVAL:
        _last_metrics_log[key] = now
        logger.info(
            "inference_admission acquired class=%s endpoint=%s wait_ms=%d "
            "active_slots=%d max_concurrency=%d utilization_percent=%d",
            kind,
            pool_id,
            waited_ms,
            active,
            MAX_CONCURRENCY,
            int(active * 100 / MAX_CONCURRENCY),
        )


@asynccontextmanager
async def inference_slot(
    kind: str, endpoint: str, *, wait_timeout_seconds: float | None = None
) -> AsyncIterator[None]:
    """Wait for a distributed endpoint slot, then release it even on cancel.

    If Redis is unavailable, inference fails open so an infrastructure hiccup
    does not make the configured model endpoint unusable. The warning makes
    the loss of cross-container fairness visible in service logs.
    """
    global _redis_warning_logged, _redis_unavailable_until
    if time.monotonic() < _redis_unavailable_until:
        tracker = admission_wait_tracker.get()
        if tracker is not None:
            tracker.append(0)
        yield
        return
    class_index, class_limit = _class_settings(kind)
    pool_id = _pool_id(endpoint)
    chat_key, batch_key, metrics_key = _keys(pool_id)
    class_key = chat_key if kind == "chat" else batch_key
    token = f"{os.getpid()}:{uuid.uuid4().hex}"
    started = time.monotonic()
    waited_ms = 0
    warned_waiting = False
    wait_limit = wait_timeout_seconds
    if wait_limit is None:
        wait_limit = CHAT_WAIT_SECONDS if kind == "chat" else BATCH_WAIT_SECONDS
    keys = (chat_key, batch_key, metrics_key)

    while True:
        if warned_waiting:
            waited_ms = int((time.monotonic() - started) * 1000)
        try:
            result = await _eval(
                _ACQUIRE_SCRIPT,
                keys,
                token,
                LEASE_MS,
                MAX_CONCURRENCY,
                class_limit,
                class_index,
                waited_ms,
            )
        except Exception:
            _redis_unavailable_until = time.monotonic() + 30.0
            if not _redis_warning_logged:
                logger.warning(
                    "Inference admission unavailable; continuing without shared endpoint limits",
                    exc_info=True,
                )
                _redis_warning_logged = True
            tracker = admission_wait_tracker.get()
            if tracker is not None:
                tracker.append(waited_ms)
            yield
            return

        acquired, active, _, _ = map(int, result)
        if acquired:
            _log_metrics(pool_id, kind, active, waited_ms)
            tracker = admission_wait_tracker.get()
            if tracker is not None:
                tracker.append(waited_ms)
            renew_task = asyncio.create_task(_renew(class_key, token))
            try:
                yield
            finally:
                renew_task.cancel()
                try:
                    await renew_task
                except asyncio.CancelledError:
                    pass
                try:
                    await _eval(
                        _RELEASE_SCRIPT,
                        (class_key, chat_key, batch_key, metrics_key),
                        token,
                        MAX_CONCURRENCY,
                    )
                except Exception:
                    logger.warning("Inference admission lease release failed", exc_info=True)
            return

        elapsed = time.monotonic() - started
        if not warned_waiting:
            logger.info(
                "inference_admission queued class=%s endpoint=%s active_slots=%d "
                "max_concurrency=%d wait_limit_seconds=%.1f",
                kind,
                pool_id,
                active,
                MAX_CONCURRENCY,
                wait_limit,
            )
            warned_waiting = True
        if elapsed >= wait_limit:
            waited_ms = int(elapsed * 1000)
            tracker = admission_wait_tracker.get()
            if tracker is not None:
                tracker.append(waited_ms)
            try:
                await _eval(_WAIT_METRIC_SCRIPT, (metrics_key,), kind, waited_ms)
            except Exception:
                _redis_unavailable_until = time.monotonic() + 30.0
            raise InferenceAdmissionTimeout(
                f"Der Modellserver ist ausgelastet: Für die {kind}-Anfrage wurde "
                f"innerhalb von {waited_ms} ms kein freier Inferenz-Slot verfügbar."
            )
        await asyncio.sleep(min(POLL_SECONDS, max(0.01, wait_limit - elapsed)))


@asynccontextmanager
async def admitted_stream(
    client: Any,
    endpoint: str,
    *,
    kind: str = "chat",
    wait_timeout_seconds: float | None = None,
    **request_kwargs: Any,
) -> AsyncIterator[Any]:
    """Run and consume a streaming model request while holding its slot."""
    async with inference_slot(kind, endpoint, wait_timeout_seconds=wait_timeout_seconds):
        async with client.stream("POST", endpoint, **request_kwargs) as response:
            yield response


async def admitted_post(
    client: Any,
    endpoint: str,
    *,
    kind: str = "batch",
    wait_timeout_seconds: float | None = None,
    **request_kwargs: Any,
) -> Any:
    """Send one non-streaming model request while holding its slot."""
    async with inference_slot(kind, endpoint, wait_timeout_seconds=wait_timeout_seconds):
        return await client.post(endpoint, **request_kwargs)
