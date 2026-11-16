"""
backend/services/agent_providers.py
===================================
Anbieter-Adapter für die Agentenschleife in agent.py.

Ein Adapter kapselt nur, was sich zwischen den Anbietern wirklich
unterscheidet: Nachrichten- und Werkzeugformat, Endpunkt und Header, wie
``tool_choice`` ausgedrückt wird und wie eine Antwort zerlegt wird.
Recherchebudget, Werkzeugausführung, erzwungene Recherche, Abschlussrunde und
Fehlerbehandlung liegen einmal in der gemeinsamen Schleife (agent.py).

Ablauf je Runde aus Sicht der Schleife:
    complete()          -> liefert Text-Stücke (nur streamende Adapter) und zuletzt einen ModelTurn
    add_tool_results()  -> hängt die Antwort des Modells samt Werkzeugergebnissen an das Gespräch
    add_user_text()     -> zusätzliche Nutzeranweisung (Abschlussrunde)
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, Union

import core.config as cfg
from doctus_models.inference_admission import admitted_post, admitted_stream
from core.inference_errors import raise_for_inference_status
from core.llm_providers import is_self_hosted_openai

logger = logging.getLogger(__name__)

# Diese Schemata nutzen optionale Felder, die der strikte Modus der OpenAI-APIs ablehnt.
_NON_STRICT_TOOLS = frozenset({"inspect_change_impact", "inspect_change_package"})

ToolChoice = Optional[str]  # None (Modell entscheidet), "required" oder "none"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Any


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Anbieterspezifische Assistenten-Nachricht, wie sie ins Gespräch zurückgeht.
    raw: Any = None
    # Vom Server gemeldete Größen des Zugs; None, wenn der Server sie nicht liefert.
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    finish_reason: Optional[str] = None


def _parse_arguments(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw if raw is not None else {}
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        return raw


def _schema(tool: dict) -> dict:
    return tool.get("inputSchema", {"type": "object", "properties": {}})


_THINK_BLOCK_RE = re.compile(r"<think>.*?(?:</think>|\Z)", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Antworttext ohne Denkabschnitte.

    Server ohne Reasoning-Parser (vLLM ohne ``--reasoning-parser``, ältere Ollama-Versionen) liefern das
    Denken von Qwen3 als ``<think>…</think>`` im Antworttext. Füllt das Chat-Template das öffnende Tag
    selbst vor, kommt nur das schließende an; dann ist alles davor Denken.
    """
    if "think>" not in text:
        return text
    text = _THINK_BLOCK_RE.sub("", text)
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[1]
    return text.lstrip()


class ThinkFilter:
    """Entfernt ``<think>…</think>`` aus gestreamtem Text, auch wenn ein Tag über eine Stückgrenze läuft."""

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False

    def feed(self, piece: str) -> str:
        self._buffer += piece
        out: list[str] = []
        while self._buffer:
            tag = "</think>" if self._inside else "<think>"
            index = self._buffer.find(tag)
            if index >= 0:
                if not self._inside:
                    out.append(self._buffer[:index])
                self._buffer = self._buffer[index + len(tag) :]
                self._inside = not self._inside
                continue
            # Ein möglicher Tag-Anfang am Ende wartet auf das nächste Stück.
            keep = next(
                (n for n in range(len(tag) - 1, 0, -1) if self._buffer.endswith(tag[:n])), 0
            )
            cut = len(self._buffer) - keep
            if not self._inside:
                out.append(self._buffer[:cut])
            self._buffer = self._buffer[cut:]
            break
        return "".join(out)

    def flush(self) -> str:
        rest, self._buffer = self._buffer, ""
        return "" if self._inside else rest


# Vorsichtige Annahme für Zeichen je Token, bis der Server echte Zahlen meldet (Deutsch und JSON).
_DEFAULT_CHARS_PER_TOKEN = 3.0
_TRIMMED_TOOL_RESULT = (
    "[Älteres Werkzeugergebnis entfernt, damit das Gespräch ins Kontextfenster des Modells passt. "
    "Bei Bedarf das Werkzeug erneut aufrufen.]"
)


def _wire_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False))


class _ChatMessageBudget:
    """Hält ein Gespräch aus ``role``/``content``-Nachrichten unter dem Kontextfenster des Profils.

    Ohne diese Grenze wächst das Gespräch über die Werkzeugrunden, bis der Server kürzt: Ollama entfernt
    dann ganze Nachrichten von vorn (zuerst Verlauf und Frage), vLLM und llama.cpp lehnen die Anfrage ab.
    Gekürzt werden nur ältere Werkzeugergebnisse; das erste (vorab geladenes Belegpaket) und das jüngste
    bleiben stehen.
    """

    context_length: Optional[int]
    messages: list[dict]
    wire_tools: list[dict]
    _chars_per_token: float = _DEFAULT_CHARS_PER_TOKEN
    _sent_chars: int = 0

    def _fit_messages(self, tools_sent: bool = True) -> None:
        size = sum(_wire_size(m) for m in self.messages)
        if tools_sent:
            size += _wire_size(self.wire_tools)
        if self.context_length:
            reserve = max(1500, self.context_length // 5)  # Antwort und Denken
            budget = (self.context_length - reserve) * self._chars_per_token
            tool_indexes = [i for i, m in enumerate(self.messages) if m.get("role") == "tool"]
            trimmed = 0
            for index in tool_indexes[1:-1]:
                if size <= budget:
                    break
                content = self.messages[index].get("content")
                if not isinstance(content, str) or len(content) <= len(_TRIMMED_TOOL_RESULT):
                    continue
                size -= len(content) - len(_TRIMMED_TOOL_RESULT)
                self.messages[index] = {**self.messages[index], "content": _TRIMMED_TOOL_RESULT}
                trimmed += 1
            if trimmed or size > budget:
                logger.warning(
                    "Gespräch nahe am Kontextfenster (%s Tokens): %s ältere Werkzeugergebnisse entfernt, "
                    "geschätzt %s von %s Zeichen",
                    self.context_length,
                    trimmed,
                    size,
                    int(budget),
                )
        self._sent_chars = size

    def _calibrate(self, prompt_tokens: Optional[int]) -> None:
        """Zeichen je Token aus der Serverangabe des letzten Zugs; ersetzt die Annahme."""
        if prompt_tokens and self._sent_chars:
            # Enge Grenzen: Bei kleinen Anfragen bläht die JSON-Hülle das Verhältnis auf, und ein
            # Server, der nur neu ausgewertete Tokens meldet, würde das Budget zu großzügig machen.
            self._chars_per_token = min(4.0, max(2.5, self._sent_chars / prompt_tokens))


class ProviderAdapter:
    provider: str
    streams = False

    def __init__(
        self,
        *,
        model_name: Optional[str],
        system_prompt: str,
        tools: list[dict],
        history: list[dict],
        prompt: str,
        temperature: Optional[float],
        context_length: Optional[int] = None,
    ):
        self.context_length = context_length
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.tools = tools
        self.temperature = temperature if temperature is not None else cfg.DEFAULT_CHAT_TEMPERATURE
        self.history = history
        self.prompt = prompt

    async def complete(
        self, client: Any, turn_index: int, tool_choice: ToolChoice
    ) -> AsyncIterator[Union[str, ModelTurn]]:
        raise NotImplementedError
        yield  # pragma: no cover

    def add_tool_results(
        self, calls: list[ToolCall], results: list[str], turn: Optional[ModelTurn]
    ) -> None:
        """``turn`` ist None für vorab ausgeführte Werkzeuge; dann wird der Aufruf nachgebildet."""
        raise NotImplementedError

    def add_user_text(self, text: str) -> None:
        raise NotImplementedError


def _openai_wire_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": _schema(tool),
                **({"strict": False} if tool["name"] in _NON_STRICT_TOOLS else {}),
            },
        }
        for tool in tools
    ]


class OpenAIChatAdapter(_ChatMessageBudget, ProviderAdapter):
    """OpenAI-kompatibles /chat/completions mit Streaming (OpenAI, vLLM, llama.cpp, weitere Server)."""

    streams = True

    def __init__(
        self,
        *,
        provider: str,
        api_key: Optional[str],
        base_url: Optional[str],
        endpoint_path: Optional[str],
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.provider = provider
        self.headers = {"Content-Type": "application/json"}
        self.model = self.model_name or "gpt-4o"
        base = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.url = f"{base}/{(endpoint_path or '/chat/completions').lstrip('/')}"
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.wire_tools = _openai_wire_tools(self.tools)
        self.messages: list[dict] = []
        if self.system_prompt:
            self.messages.append({"role": "system", "content": self.system_prompt})
        self.messages.extend({"role": m["role"], "content": m["content"]} for m in self.history)
        self.messages.append({"role": "user", "content": self.prompt})

    async def complete(self, client, turn_index, tool_choice):
        self._fit_messages()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "tools": self.wire_tools,
            "stream": True,
            # Ohne diese Angabe meldet ein Streaming-Server keinen Tokenverbrauch.
            "stream_options": {"include_usage": True},
        }
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if cfg.openai_model_supports_custom_temperature(self.model):
            payload["temperature"] = self.temperature

        raw_text = ""
        think_filter = ThinkFilter()
        partial_calls: dict[int, dict] = {}
        usage: dict = {}
        finish_reason: Optional[str] = None
        async with admitted_stream(
            client, self.url, kind="chat", json=payload, headers=self.headers
        ) as resp:
            raise_for_inference_status(resp, self.provider)
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]
                if not chunk.get("choices"):
                    continue
                choice = chunk["choices"][0]
                finish_reason = choice.get("finish_reason") or finish_reason
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    raw_text += delta["content"]
                    visible = think_filter.feed(delta["content"])
                    if visible:
                        yield visible
                for part in delta.get("tool_calls") or []:
                    function = part.get("function") or {}
                    call = partial_calls.setdefault(
                        part.get("index", 0),
                        {"id": None, "type": None, "function": {"name": "", "arguments": ""}},
                    )
                    call["id"] = part.get("id") or call["id"]
                    call["type"] = part.get("type") or call["type"]
                    call["function"]["name"] = function.get("name") or call["function"]["name"]
                    call["function"]["arguments"] += function.get("arguments") or ""
        rest = think_filter.flush()
        if rest:
            yield rest

        text = strip_thinking(raw_text)
        tool_calls: list[ToolCall] = []
        wire_calls: list[dict] = []
        for index, call in sorted(partial_calls.items()):
            call_id = call["id"] or f"tc-{turn_index}-{index}"
            arguments = _parse_arguments(call["function"]["arguments"])
            tool_calls.append(ToolCall(call_id, call["function"]["name"], arguments))
            wire_calls.append(
                {
                    "id": call_id,
                    "type": call["type"] or "function",
                    "function": {
                        "name": call["function"]["name"],
                        # Ungültiges JSON geht nicht zurück an den Server; er würde die nächste Anfrage
                        # ablehnen. Die Schleife meldet dem Modell den Fehler als Werkzeugergebnis.
                        "arguments": call["function"]["arguments"]
                        if isinstance(arguments, dict)
                        else "{}",
                    },
                }
            )
        raw = {"role": "assistant", "content": text or None}
        if wire_calls:
            raw["tool_calls"] = wire_calls
        self._calibrate(usage.get("prompt_tokens"))
        yield ModelTurn(
            text=text,
            tool_calls=tool_calls,
            raw=raw,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            finish_reason=finish_reason,
        )

    def add_tool_results(self, calls, results, turn):
        self.messages.append(
            turn.raw
            if turn is not None
            else {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                    }
                    for call in calls
                ],
            }
        )
        self.messages.extend(
            {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": result}
            for call, result in zip(calls, results)
        )

    def add_user_text(self, text):
        self.messages.append({"role": "user", "content": text})


class OllamaChatAdapter(_ChatMessageBudget, ProviderAdapter):
    """Ollamas natives ``/api/chat``.

    Der OpenAI-kompatible Pfad ``/v1/chat/completions`` kennt weder ``num_ctx`` noch ``tool_choice``: Das
    Kontextfenster ließe sich dort nicht je Anfrage setzen, und Ollama fiele auf die Servervorgabe zurück.
    Nur der native Pfad nimmt ``options.num_ctx`` an und liefert das Denken getrennt in ``message.thinking``.
    """

    provider = "ollama"
    streams = True

    def __init__(
        self,
        *,
        api_key: Optional[str],
        endpoint_path: Optional[str],
        ollama_base_url: str,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.headers = {"Content-Type": "application/json"}
        # Ein entferntes Ollama-Profil bringt ggf. eigene Zugangsdaten mit;
        # der prozessweite Wert ist nur der Rückfall für das lokale Profil (O-259).
        key = api_key or cfg.OLLAMA_API_KEY
        if key:
            self.headers["Authorization"] = f"Bearer {key}"
        self.model = cfg.resolve_ollama_model(self.model_name)
        self.url = f"{ollama_base_url.rstrip('/')}/{(endpoint_path or '/api/chat').lstrip('/')}"
        self.num_ctx = self.context_length or cfg.OLLAMA_NUM_CTX
        self.context_length = self.num_ctx
        self.wire_tools = _openai_wire_tools(self.tools)
        self.messages: list[dict] = []
        if self.system_prompt:
            self.messages.append({"role": "system", "content": self.system_prompt})
        self.messages.extend({"role": m["role"], "content": m["content"]} for m in self.history)
        self.messages.append({"role": "user", "content": self.prompt})

    async def complete(self, client, turn_index, tool_choice):
        # Ollama kennt kein ``tool_choice``. "none" wird durch Weglassen der Werkzeuge erreicht; "required"
        # lässt sich nicht erzwingen, die Schleife verwirft eine Antwort ohne Recherche und wiederholt.
        offer_tools = tool_choice != "none"
        self._fit_messages(tools_sent=offer_tools)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "stream": True,
            # O-168: explizites Kontextfenster statt Ollamas stillschweigend kürzender Servervorgabe.
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if offer_tools:
            payload["tools"] = self.wire_tools

        raw_text = ""
        # Ältere Ollama-Versionen liefern das Denken noch im Antworttext statt in ``message.thinking``.
        think_filter = ThinkFilter()
        wire_calls: list[dict] = []
        done: dict = {}
        async with admitted_stream(
            client, self.url, kind="chat", json=payload, headers=self.headers
        ) as resp:
            raise_for_inference_status(resp, self.provider)
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("error"):
                    raise RuntimeError(f"Ollama meldet einen Fehler: {chunk['error']}")
                message = chunk.get("message") or {}
                if message.get("content"):
                    raw_text += message["content"]
                    visible = think_filter.feed(message["content"])
                    if visible:
                        yield visible
                wire_calls.extend(message.get("tool_calls") or [])
                if chunk.get("done"):
                    done = chunk
                    break
        rest = think_filter.flush()
        if rest:
            yield rest

        text = strip_thinking(raw_text)
        tool_calls = []
        for index, call in enumerate(wire_calls):
            function = call.get("function") or {}
            call.setdefault("id", f"tc-{turn_index}-{index}")
            tool_calls.append(
                ToolCall(call["id"], function.get("name", ""), function.get("arguments") or {})
            )
        raw: dict[str, Any] = {"role": "assistant", "content": text}
        if wire_calls:
            raw["tool_calls"] = wire_calls
        self._calibrate(done.get("prompt_eval_count"))
        yield ModelTurn(
            text=text,
            tool_calls=tool_calls,
            raw=raw,
            prompt_tokens=done.get("prompt_eval_count"),
            completion_tokens=done.get("eval_count"),
            finish_reason=done.get("done_reason"),
        )

    def add_tool_results(self, calls, results, turn):
        self.messages.append(
            turn.raw
            if turn is not None
            else {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": call.id, "function": {"name": call.name, "arguments": call.arguments}}
                    for call in calls
                ],
            }
        )
        self.messages.extend(
            {"role": "tool", "tool_call_id": call.id, "tool_name": call.name, "content": result}
            for call, result in zip(calls, results)
        )

    def add_user_text(self, text):
        self.messages.append({"role": "user", "content": text})


class OpenAIResponsesAdapter(ProviderAdapter):
    """OpenAI Responses API: flache Werkzeugdefinitionen, Ergebnisse als ``function_call_output``."""

    provider = "openai_responses"

    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: Optional[str],
        endpoint_path: Optional[str],
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.model = self.model_name or "gpt-4o"
        base = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.url = f"{base}/{(endpoint_path or '/responses').lstrip('/')}"
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.wire_tools = [
            {
                "type": "function",
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": _schema(tool),
                **({"strict": False} if tool["name"] in _NON_STRICT_TOOLS else {}),
            }
            for tool in self.tools
        ]
        self.input: list[dict] = [
            {"role": m["role"], "content": m["content"]} for m in self.history
        ]
        self.input.append({"role": "user", "content": self.prompt})

    async def complete(self, client, turn_index, tool_choice):
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": self.system_prompt,
            "input": self.input,
            "tools": self.wire_tools,
            "stream": False,
        }
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if cfg.openai_model_supports_custom_temperature(self.model):
            payload["temperature"] = self.temperature
        resp = await admitted_post(
            client, self.url, kind="chat", json=payload, headers=self.headers
        )
        raise_for_inference_status(resp, self.provider)
        data = resp.json()
        items = data.get("output", [])
        texts: list[str] = []
        calls: list[ToolCall] = []
        for item in items:
            if item.get("type") == "message":
                texts.extend(
                    content["text"]
                    for content in item.get("content", [])
                    if content.get("type") == "output_text" and content.get("text")
                )
            elif item.get("type") == "function_call":
                calls.append(
                    ToolCall(
                        item.get("call_id") or item.get("id") or f"tc-{turn_index}-{len(calls)}",
                        item.get("name", ""),
                        _parse_arguments(item.get("arguments", "")),
                    )
                )
        # Die Ausgabe-Items sind der Assistenten-Zug, auf den sich die Ergebnisse beziehen.
        yield ModelTurn(
            text="".join(texts) or data.get("output_text", ""), tool_calls=calls, raw=items
        )

    def add_tool_results(self, calls, results, turn):
        if turn is not None:
            self.input.extend(turn.raw)
        else:
            self.input.extend(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                }
                for call in calls
            )
        self.input.extend(
            {"type": "function_call_output", "call_id": call.id, "output": result}
            for call, result in zip(calls, results)
        )

    def add_user_text(self, text):
        self.input.append({"role": "user", "content": text})


class AnthropicAdapter(ProviderAdapter):
    provider = "anthropic"
    _TOOL_CHOICE = {"required": {"type": "any"}, "none": {"type": "none"}}

    def __init__(self, *, api_key: Optional[str], **kwargs: Any):
        super().__init__(**kwargs)
        self.url = "https://api.anthropic.com/v1/messages"
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key or "",
            "anthropic-version": "2023-06-01",
        }
        self.wire_tools = [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": _schema(tool),
            }
            for tool in self.tools
        ]
        self.messages: list[dict] = [
            {"role": m["role"], "content": m["content"]} for m in self.history
        ]
        self.messages.append({"role": "user", "content": self.prompt})

    async def complete(self, client, turn_index, tool_choice):
        payload: dict[str, Any] = {
            "model": self.model_name or "claude-3-5-sonnet-20241022",
            "max_tokens": 4096,
            "messages": self.messages,
            "temperature": self.temperature,
            "tools": self.wire_tools,
        }
        if self.system_prompt:
            payload["system"] = self.system_prompt
        if tool_choice:
            payload["tool_choice"] = self._TOOL_CHOICE[tool_choice]
        resp = await admitted_post(
            client, self.url, kind="chat", json=payload, headers=self.headers
        )
        raise_for_inference_status(resp, self.provider)
        blocks = resp.json()["content"]
        yield ModelTurn(
            text="".join(b.get("text", "") for b in blocks if b.get("type") == "text"),
            tool_calls=[
                ToolCall(b["id"], b["name"], b.get("input") or {})
                for b in blocks
                if b.get("type") == "tool_use"
            ],
            raw={"role": "assistant", "content": blocks},
        )

    def add_tool_results(self, calls, results, turn):
        self.messages.append(
            turn.raw
            if turn is not None
            else {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                    for call in calls
                ],
            }
        )
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": call.id, "content": result}
                    for call, result in zip(calls, results)
                ],
            }
        )

    def add_user_text(self, text):
        # Aufeinanderfolgende Nutzerzüge werden zu einem zusammengeführt.
        last = self.messages[-1]
        if last["role"] == "user" and isinstance(last["content"], list):
            last["content"].append({"type": "text", "text": text})
        else:
            self.messages.append({"role": "user", "content": text})


class GeminiAdapter(ProviderAdapter):
    provider = "gemini"
    _TOOL_MODE = {"required": "ANY", "none": "NONE"}

    def __init__(self, *, api_key: Optional[str], **kwargs: Any):
        super().__init__(**kwargs)
        model = self.model_name or "gemini-1.5-flash"
        self.url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={api_key}"
        )
        self.headers = {"Content-Type": "application/json"}
        self.wire_tools = [
            {
                "functionDeclarations": [
                    {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": _schema(tool),
                    }
                    for tool in self.tools
                ]
            }
        ]
        self.contents: list[dict] = [
            {
                "role": "user" if m["role"] == "user" else "model",
                "parts": [{"text": m["content"]}],
            }
            for m in self.history
        ]
        self.contents.append({"role": "user", "parts": [{"text": self.prompt}]})

    async def complete(self, client, turn_index, tool_choice):
        payload: dict[str, Any] = {
            "contents": self.contents,
            "tools": self.wire_tools,
            "generationConfig": {"temperature": self.temperature},
        }
        if self.system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": self.system_prompt}]}
        if tool_choice:
            payload["toolConfig"] = {
                "functionCallingConfig": {"mode": self._TOOL_MODE[tool_choice]}
            }
        resp = await admitted_post(
            client, self.url, kind="chat", json=payload, headers=self.headers
        )
        raise_for_inference_status(resp, self.provider)
        content = resp.json()["candidates"][0]["content"]
        parts = content.get("parts", [])
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        yield ModelTurn(
            text="".join(p.get("text", "") for p in parts if "text" in p),
            tool_calls=[
                ToolCall(f"tc-{turn_index}-{index}", call["name"], call.get("args", {}))
                for index, call in enumerate(calls)
            ],
            raw=content,
        )

    def add_tool_results(self, calls, results, turn):
        self.contents.append(
            turn.raw
            if turn is not None
            else {
                "role": "model",
                "parts": [
                    {"functionCall": {"name": call.name, "args": call.arguments}} for call in calls
                ],
            }
        )
        self.contents.append(
            {
                "role": "user",
                "parts": [
                    {"functionResponse": {"name": call.name, "response": {"result": result}}}
                    for call, result in zip(calls, results)
                ],
            }
        )

    def add_user_text(self, text):
        last = self.contents[-1]
        if last["role"] == "user":
            last["parts"].append({"text": text})
        else:
            self.contents.append({"role": "user", "parts": [{"text": text}]})


def make_provider_adapter(
    provider: str,
    *,
    api_key: Optional[str],
    base_url: Optional[str],
    endpoint_path: Optional[str],
    ollama_base_url: str,
    **conversation: Any,
) -> Optional[ProviderAdapter]:
    """Adapter für ``provider`` oder None, wenn es für ihn keine Werkzeugschleife gibt."""
    if provider == "openai_responses":
        return OpenAIResponsesAdapter(
            api_key=api_key, base_url=base_url, endpoint_path=endpoint_path, **conversation
        )
    if provider == "ollama":
        return OllamaChatAdapter(
            api_key=api_key,
            endpoint_path=endpoint_path,
            ollama_base_url=ollama_base_url,
            **conversation,
        )
    if provider == "openai" or is_self_hosted_openai(provider):
        return OpenAIChatAdapter(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            endpoint_path=endpoint_path,
            **conversation,
        )
    if provider == "anthropic":
        return AnthropicAdapter(api_key=api_key, **conversation)
    if provider == "gemini":
        return GeminiAdapter(api_key=api_key, **conversation)
    return None
