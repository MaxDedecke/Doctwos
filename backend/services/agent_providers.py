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
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, Union

import core.config as cfg
from core.inference_admission import admitted_post, admitted_stream
from core.inference_errors import raise_for_inference_status
from core.llm_providers import is_self_hosted_openai

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


def _parse_arguments(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw if raw is not None else {}
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        return raw


def _schema(tool: dict) -> dict:
    return tool.get("inputSchema", {"type": "object", "properties": {}})


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
    ):
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


class OpenAIChatAdapter(ProviderAdapter):
    """OpenAI-kompatibles /chat/completions mit Streaming (OpenAI, Ollama, selbst gehostete Server)."""

    streams = True

    def __init__(
        self,
        *,
        provider: str,
        api_key: Optional[str],
        base_url: Optional[str],
        endpoint_path: Optional[str],
        ollama_base_url: str,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.provider = provider
        self.is_ollama = provider == "ollama"
        self.headers = {"Content-Type": "application/json"}
        if self.is_ollama:
            # Ein entferntes Ollama-Profil bringt ggf. eigene Zugangsdaten mit;
            # der prozessweite Wert ist nur der Rückfall für das lokale Profil (O-259).
            key = api_key or cfg.OLLAMA_API_KEY
            self.model = cfg.resolve_ollama_model(self.model_name)
            self.url = f"{ollama_base_url}/v1/chat/completions"
        else:
            key = api_key
            self.model = self.model_name or "gpt-4o"
            base = (base_url or "https://api.openai.com/v1").rstrip("/")
            self.url = f"{base}/{(endpoint_path or '/chat/completions').lstrip('/')}"
        if key:
            self.headers["Authorization"] = f"Bearer {key}"
        self.wire_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": _schema(tool),
                    **({"strict": False} if tool["name"] in _NON_STRICT_TOOLS else {}),
                },
            }
            for tool in self.tools
        ]
        self.messages: list[dict] = []
        if self.system_prompt:
            self.messages.append({"role": "system", "content": self.system_prompt})
        self.messages.extend({"role": m["role"], "content": m["content"]} for m in self.history)
        self.messages.append({"role": "user", "content": self.prompt})

    async def complete(self, client, turn_index, tool_choice):
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "tools": self.wire_tools,
            "stream": True,
        }
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if self.is_ollama or cfg.openai_model_supports_custom_temperature(self.model):
            payload["temperature"] = self.temperature
        if self.is_ollama:
            # O-168: explizites Kontextfenster statt Ollamas kleinem, stillschweigend
            # kürzendem Default; die Werkzeugschleife hängt über mehrere Runden an.
            payload["num_ctx"] = cfg.OLLAMA_NUM_CTX

        text = ""
        partial_calls: dict[int, dict] = {}
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
                if not chunk.get("choices"):
                    continue
                delta = chunk["choices"][0].get("delta", {})
                if delta.get("content"):
                    text += delta["content"]
                    yield delta["content"]
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

        wire_calls = [
            {
                "id": call["id"] or f"tc-{turn_index}-{index}",
                "type": call["type"] or "function",
                "function": call["function"],
            }
            for index, call in sorted(partial_calls.items())
        ]
        raw = {"role": "assistant", "content": text or None}
        if wire_calls:
            raw["tool_calls"] = wire_calls
        yield ModelTurn(
            text=text,
            tool_calls=[
                ToolCall(
                    call["id"],
                    call["function"]["name"],
                    _parse_arguments(call["function"]["arguments"]),
                )
                for call in wire_calls
            ],
            raw=raw,
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
    if provider in {"openai", "ollama"} or is_self_hosted_openai(provider):
        return OpenAIChatAdapter(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            endpoint_path=endpoint_path,
            ollama_base_url=ollama_base_url,
            **conversation,
        )
    if provider == "anthropic":
        return AnthropicAdapter(api_key=api_key, **conversation)
    if provider == "gemini":
        return GeminiAdapter(api_key=api_key, **conversation)
    return None
