"""Provider-aware inference errors that are safe to show in the chat UI."""

from __future__ import annotations

import json

import httpx

from core.llm_providers import is_self_hosted_openai, provider_label


class VllmCapacityError(RuntimeError):
    """A self-hosted server (vLLM, llama.cpp) rejected inference for lack of capacity.

    The name is kept for existing callers; it covers every provider in
    ``SELF_HOSTED_OPENAI_PROVIDERS``.
    """


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
    # Request larger than the context the server was started with
    # (vLLM --max-model-len, llama-server -c / --ctx-size).
    "maximum context length",
    "exceed_context_size",
    "available context size",
    # llama-server while the model is still loading or no slot is free.
    "loading model",
    "no slot available",
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
    """Raise an actionable capacity error for self-hosted servers, otherwise preserve HTTPX errors."""
    if response.is_success:
        return
    if is_self_hosted_openai(provider):
        detail = _response_detail(response).lower()
        if response.status_code in {429, 503} or any(marker in detail for marker in _VLLM_MEMORY_MARKERS):
            raise VllmCapacityError(
                f"{provider_label(provider)} ist ausgelastet oder hat nicht genug GPU-/KV-Cache-Speicher "
                "bzw. Kontext für diese Anfrage. Bitte erneut versuchen oder Kontextlänge, "
                "Parallelität bzw. Modellgröße reduzieren."
            )
    response.raise_for_status()
