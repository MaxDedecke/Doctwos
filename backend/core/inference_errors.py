"""Provider-aware inference errors that are safe to show in the chat UI."""

from __future__ import annotations

import json

import httpx


class VllmCapacityError(RuntimeError):
    """vLLM rejected inference because the serving capacity is exhausted."""


_VLLM_MEMORY_MARKERS = (
    "out of memory",
    "cuda oom",
    "gpu memory",
    "kv cache",
    "kv_cache",
    "no available memory",
    "failed to allocate",
    "memory exhausted",
    "torch.cuda",
)


def _response_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return response.text[:2000]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("detail") or error)[:2000]
        if isinstance(error, str):
            return error[:2000]
        if payload.get("detail"):
            return str(payload["detail"])[:2000]
    return ""


def raise_for_inference_status(response: httpx.Response, provider: str | None) -> None:
    """Raise an actionable vLLM capacity error, otherwise preserve HTTPX errors."""
    if response.is_success:
        return
    if (provider or "").lower() == "vllm":
        detail = _response_detail(response).lower()
        if response.status_code in {429, 503} or any(marker in detail for marker in _VLLM_MEMORY_MARKERS):
            raise VllmCapacityError(
                "vLLM ist ausgelastet oder hat nicht genug GPU-/KV-Cache-Speicher für diese Anfrage. "
                "Bitte erneut versuchen oder Kontextlänge, Parallelität bzw. Modellgröße reduzieren."
            )
    response.raise_for_status()
