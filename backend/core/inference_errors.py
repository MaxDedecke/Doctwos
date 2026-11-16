"""Provider-aware inference errors that are safe to show in the chat UI."""

from __future__ import annotations

import json
import re

import httpx

from core.llm_providers import is_self_hosted_openai, provider_label


class VllmCapacityError(RuntimeError):
    """A self-hosted server (vLLM, llama.cpp) rejected inference for lack of capacity.

    The name is kept for existing callers; it covers every provider in
    ``SELF_HOSTED_OPENAI_PROVIDERS``.
    """


class ContextWindowExceeded(RuntimeError):
    """The request does not fit into the context window the model server runs with.

    ``prompt_tokens`` and ``context_tokens`` are the server's own counts when it reports them.
    """

    def __init__(self, prompt_tokens: int | None = None, context_tokens: int | None = None):
        self.prompt_tokens = prompt_tokens
        self.context_tokens = context_tokens
        size = (
            f" ({prompt_tokens} Tokens bei einem Fenster von {context_tokens})"
            if prompt_tokens and context_tokens
            else ""
        )
        super().__init__(
            f"Die Anfrage passt nicht in das Kontextfenster des Modells{size}. Bitte die Kontextlänge "
            "im KI-Profil und am Modellserver erhöhen oder eine neue Unterhaltung beginnen."
        )


# Ollama and llama.cpp: {"type": "exceed_context_size_error", "n_prompt_tokens": 7258, "n_ctx": 2048}
_LLAMA_OVERFLOW_RE = re.compile(
    r'n_prompt_tokens\\*"\s*:\s*(\d+).*?n_ctx\\*"\s*:\s*(\d+)', re.DOTALL
)
# vLLM: "maximum context length is 8192 tokens. However, you requested 9000 tokens (8000 in the messages, …"
_VLLM_OVERFLOW_RE = re.compile(
    r"maximum context length is (\d+) tokens.*?(\d+) (?:input tokens|tokens? in the messages|in the messages)",
    re.DOTALL,
)
_OVERFLOW_MARKERS = ("exceed_context_size", "maximum context length", "available context size")


def context_overflow(detail: str) -> ContextWindowExceeded | None:
    """Recognise a server's "prompt too long" answer; None for every other error."""
    lowered = detail.lower()
    if not any(marker in lowered for marker in _OVERFLOW_MARKERS):
        return None
    match = _LLAMA_OVERFLOW_RE.search(detail)
    if match:
        return ContextWindowExceeded(int(match.group(1)), int(match.group(2)))
    match = _VLLM_OVERFLOW_RE.search(detail)
    if match:
        return ContextWindowExceeded(int(match.group(2)), int(match.group(1)))
    return ContextWindowExceeded()


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


def _response_text(response: httpx.Response) -> str:
    try:
        return response.text[:4000]
    except httpx.ResponseNotRead:
        return ""


async def raise_for_stream_status(response: httpx.Response, provider: str | None) -> None:
    """``raise_for_inference_status`` for a streamed response, whose error body must be read first."""
    if getattr(response, "is_success", True):
        return
    await response.aread()
    raise_for_inference_status(response, provider)


def raise_for_inference_status(response: httpx.Response, provider: str | None) -> None:
    """Raise an actionable capacity error for self-hosted servers, otherwise preserve HTTPX errors."""
    if response.is_success:
        return
    overflow = context_overflow(_response_text(response))
    if overflow is not None:
        raise overflow
    if is_self_hosted_openai(provider):
        detail = _response_detail(response).lower()
        if response.status_code in {429, 503} or any(
            marker in detail for marker in _VLLM_MEMORY_MARKERS
        ):
            raise VllmCapacityError(
                f"{provider_label(provider)} ist ausgelastet oder hat nicht genug GPU-/KV-Cache-Speicher "
                "bzw. Kontext für diese Anfrage. Bitte erneut versuchen oder Kontextlänge, "
                "Parallelität bzw. Modellgröße reduzieren."
            )
    response.raise_for_status()
