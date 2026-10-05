"""Provider facts shared by profile validation, health probes and request code.

vLLM and llama.cpp (``llama-server``) are self-hosted servers that expose the
OpenAI Chat Completions API. They share the request path with OpenAI but differ
in capacity behaviour and in how tool calling has to be enabled on the server.
"""

from __future__ import annotations

SELF_HOSTED_OPENAI_PROVIDERS = frozenset({"vllm", "llamacpp"})

PROVIDER_LABELS = {"vllm": "vLLM", "llamacpp": "llama.cpp"}

# Hint shown when the forced tool call of the profile test is not honoured.
TOOL_CALLING_HINTS = {
    "vllm": (
        "Prüfe vLLM >= 0.8.3, --enable-auto-tool-choice, --tool-call-parser und das "
        "Chat-Template des Modells."
    ),
    "llamacpp": (
        "Starte llama-server mit --jinja (und bei Bedarf --chat-template-file), "
        "damit das Chat-Template des Modells Tool-Aufrufe unterstützt."
    ),
}

# Default base URL used when a profile omits one (Compose service names).
DEFAULT_BASE_URLS = {
    "vllm": "http://vllm:8000/v1",
    "llamacpp": "http://llamacpp:8080/v1",
}


def is_self_hosted_openai(provider: str | None) -> bool:
    return (provider or "").lower() in SELF_HOSTED_OPENAI_PROVIDERS


def provider_label(provider: str | None) -> str:
    return PROVIDER_LABELS.get((provider or "").lower(), provider or "LLM")
