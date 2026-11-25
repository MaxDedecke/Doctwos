"""
backend/services/standard_chat.py
=================================
Antwort ohne Werkzeuge (normaler Chat, Standard-RAG) als einheitliche Ereignisse, je Protokoll ein Zweig.

Ereignisse: ``content_chunk`` (sichtbarer Text), ``content_reset`` (bisheriger Live-Text war Denken),
``reasoning_chunk`` (getrennt geliefertes Denken), am Ende ``turn_completed`` und ``answer``; bei einem
Fehler ``error`` statt der Antwort. Das Denken landet als Arbeitsschritt ``reasoning`` in der Antwort.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import httpx

import core.config as cfg
from core.inference_errors import ContextWindowExceeded, raise_for_stream_status
from codena_models.database import ChatMessage
from codena_models.inference_admission import admitted_post, admitted_stream
from services.agent_providers import fit_chat_messages
from services.think_filter import ThinkFilter, reasoning_step, strip_thinking

logger = logging.getLogger(__name__)


@dataclass
class _Request:
    provider: str
    model: Optional[str]
    api_key: Optional[str]
    base_url: Optional[str]
    temperature: Optional[float]
    system_prompt: str
    history: list[dict]
    prompt: str
    path: Optional[str]
    context_length: Optional[int]
    reasoning_summary: bool

    @property
    def sampling_temperature(self) -> float:
        return self.temperature if self.temperature is not None else cfg.DEFAULT_CHAT_TEMPERATURE


@dataclass
class _Result:
    answer: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)


def _reasoning_event(result: _Result, text: str) -> dict:
    result.reasoning.append(text)
    return {"type": "reasoning_chunk", "turn": 0, "content": text}


async def _chat_completions(
    request: _Request, result: _Result, ollama: bool
) -> AsyncIterator[dict]:
    """Ollama ``/api/chat`` und OpenAI-kompatibles ``/chat/completions``, beide gestreamt."""
    headers = {"Content-Type": "application/json"}
    if ollama:
        base = (request.base_url or cfg.default_ollama_base_url()).rstrip("/")
        url = f"{base}/{(request.path or '/api/chat').lstrip('/')}"
        key = cfg.ollama_fallback_key(base) if request.api_key is None else request.api_key
        payload: dict[str, Any] = {
            "model": cfg.resolve_ollama_model(request.model),
            "stream": True,
            # Ohne diesen Schalter entfernt Ollama bei Überlauf still ganze Nachrichten
            # von vorn; so lehnt es die Anfrage stattdessen erkennbar ab.
            "truncate": False,
            # Ollamas /api/chat liest Sampling-Werte nur aus ``options``. O-168: explizites
            # Kontextfenster statt Ollamas kleinem, stillschweigend kürzendem Default.
            "options": {
                "temperature": request.sampling_temperature,
                "num_ctx": request.context_length or cfg.OLLAMA_NUM_CTX,
            },
        }
    else:
        base = (request.base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base}/{(request.path or '/chat/completions').lstrip('/')}"
        key = request.api_key
        model = request.model or "gpt-4o"
        payload = {"model": model, "stream": True}
        if cfg.openai_model_supports_custom_temperature(model):
            payload["temperature"] = request.sampling_temperature
    if key:
        headers["Authorization"] = f"Bearer {key}"
    # Verlauf und abgerufener Kontext weichen zuerst; Systemtext und Frage bleiben stehen.
    payload["messages"] = fit_chat_messages(
        request.system_prompt,
        request.history,
        request.prompt,
        (request.context_length or cfg.OLLAMA_NUM_CTX) if ollama else request.context_length,
    )

    raw: list[str] = []
    think_filter = ThinkFilter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with admitted_stream(
            client, url, kind="chat", json=payload, headers=headers
        ) as response:
            await raise_for_stream_status(response, request.provider)
            async for line in response.aiter_lines():
                data = (
                    line.strip()
                    if ollama
                    else line[6:].strip()
                    if line.startswith("data: ")
                    else ""
                )
                if not data:
                    continue
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError as exc:
                    logger.error("Fehler beim Parsen des Stream-Chunks: %s", exc)
                    continue
                if ollama:
                    part = chunk.get("message") or {}
                    thought = part.get("thinking")
                elif chunk.get("choices"):
                    part = chunk["choices"][0].get("delta") or {}
                    thought = part.get("reasoning_content") or part.get("reasoning")
                else:
                    continue
                if isinstance(thought, str) and thought:
                    yield _reasoning_event(result, thought)
                content = part.get("content")
                if not content:
                    continue
                raw.append(content)
                visible = think_filter.feed(content)
                thought = think_filter.take_reasoning()
                if thought:
                    yield _reasoning_event(result, thought)
                if think_filter.take_reset():
                    yield {"type": "content_reset"}
                if visible:
                    yield {"type": "content_chunk", "content": visible}
    rest = think_filter.flush()
    thought = think_filter.take_reasoning()
    if thought:
        yield _reasoning_event(result, thought)
    if rest:
        yield {"type": "content_chunk", "content": rest}
    result.answer.append(strip_thinking("".join(raw)))


async def _responses(request: _Request, result: _Result) -> AsyncIterator[dict]:
    """OpenAI Responses API, gestreamt; ohne Abschlussereignis gilt die Antwort als abgebrochen."""
    base = (request.base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/{(request.path or '/responses').lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if request.api_key:
        headers["Authorization"] = f"Bearer {request.api_key}"
    payload: dict[str, Any] = {
        "model": request.model,
        "instructions": request.system_prompt,
        "input": [*request.history, {"role": "user", "content": request.prompt}],
        "stream": True,
    }
    if request.reasoning_summary:
        payload["reasoning"] = {"summary": "auto"}
    completed = False
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with admitted_stream(
            client, url, kind="chat", json=payload, headers=headers
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                kind, delta = event.get("type"), event.get("delta")
                if kind == "response.output_text.delta" and isinstance(delta, str):
                    result.answer.append(delta)
                    yield {"type": "content_chunk", "content": delta}
                elif kind == "response.reasoning_summary_text.delta" and isinstance(delta, str):
                    yield _reasoning_event(result, delta)
                elif kind in ("response.completed", "response.incomplete"):
                    completed = True
                elif kind in ("response.failed", "error"):
                    error = (event.get("response") or {}).get("error") or event
                    raise RuntimeError(
                        f"Responses API meldet einen Fehler: {error.get('message') or error}"
                    )
    if not completed:
        raise RuntimeError("Der Responses-Stream endete ohne Abschlussereignis.")


async def _gemini(request: _Request, result: _Result) -> AsyncIterator[dict]:
    model_name = request.model or "gemini-1.5-flash"
    contents = [
        {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
        for m in request.history
    ]
    contents.append({"role": "user", "parts": [{"text": request.prompt}]})
    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {"temperature": request.sampling_temperature},
    }
    if request.system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}
    base = (request.base_url or "https://generativelanguage.googleapis.com").rstrip("/")
    path = (request.path or "/v1beta/models/{model}:generateContent").replace("{model}", model_name)
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await admitted_post(
            client,
            f"{base}/{path.lstrip('/')}?key={request.api_key or ''}",
            kind="chat",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    result.answer.append(answer)
    yield {"type": "content_chunk", "content": answer}


async def _anthropic(request: _Request, result: _Result) -> AsyncIterator[dict]:
    messages = [*request.history, {"role": "user", "content": request.prompt}]
    payload: dict[str, Any] = {
        "model": request.model or "claude-3-5-sonnet-20241022",
        "max_tokens": 4096,
        "messages": messages,
        "temperature": request.sampling_temperature,
    }
    if request.system_prompt:
        payload["system"] = request.system_prompt
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await admitted_post(
            client,
            f"{(request.base_url or 'https://api.anthropic.com/v1').rstrip('/')}/"
            f"{(request.path or '/messages').lstrip('/')}",
            kind="chat",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": request.api_key or "",
                "anthropic-version": "2023-06-01",
            },
        )
        response.raise_for_status()
        answer = response.json()["content"][0]["text"]
    result.answer.append(answer)
    yield {"type": "content_chunk", "content": answer}


async def stream_standard_rag_events(
    *,
    provider: str,
    model: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
    temperature: Optional[float],
    system_prompt: str,
    history: list[ChatMessage],
    prompt: str,
    protocol: Optional[str] = None,
    path: Optional[str] = None,
    context_length: Optional[int] = None,
    reasoning_summary: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    """Stream a non-agent provider response as normalized chat events."""
    request = _Request(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        system_prompt=system_prompt,
        history=[{"role": message.role, "content": message.content} for message in history],
        prompt=prompt,
        path=path,
        context_length=context_length,
        reasoning_summary=reasoning_summary,
    )
    result = _Result()
    selected = protocol or ("ollama" if provider == "ollama" else "openai_chat")
    branches = {
        "openai_chat": lambda: _chat_completions(request, result, ollama=False),
        "ollama": lambda: _chat_completions(request, result, ollama=True),
        "openai_responses": lambda: _responses(request, result),
        "gemini": lambda: _gemini(request, result),
        "anthropic": lambda: _anthropic(request, result),
    }
    try:
        if selected in branches:
            async for event in branches[selected]():
                yield event
        thinking = reasoning_step(0, "".join(result.reasoning))
        yield {"type": "turn_completed", "has_tool_calls": False}
        yield {
            "type": "answer",
            "content": "".join(result.answer),
            "agent_steps": [thinking] if thinking else [],
        }
    except ContextWindowExceeded as exc:
        logger.error("Standard-Chat passt nicht ins Kontextfenster: %s", exc)
        yield {"type": "error", "error": str(exc)}
    except Exception as exc:
        error_detail = f"Fehler bei der Kommunikation mit dem LLM-Provider ({provider}): {exc}"
        logger.error(error_detail)
        yield {"type": "error", "error": error_detail}
