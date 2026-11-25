"""
backend/services/agent_providers_hosted.py
==========================================
Adapter der gehosteten APIs für die Agentenschleife: OpenAI Responses, Anthropic Messages, Gemini.

Der gemeinsame Vertrag (``complete()``, ``add_tool_results()``, ``add_user_text()``) und die Adapter der
selbst betriebenen Server (Ollama, OpenAI-kompatibles Chat Completions) stehen in
``services/agent_providers.py``.
"""

import json
from typing import Any, Optional

import core.config as cfg
from core.inference_errors import raise_for_inference_status, raise_for_stream_status
from codena_models.inference_admission import admitted_post, admitted_stream
from services.agent_providers import (
    _NON_STRICT_TOOLS,
    ModelTurn,
    ProviderAdapter,
    Reasoning,
    ToolCall,
    _ChatMessageBudget,
    _parse_arguments,
    _schema,
)


class ResponsesStreamError(RuntimeError):
    """Die Responses API meldete im Stream einen Fehler oder brach ohne Abschluss ab."""


class OpenAIResponsesAdapter(_ChatMessageBudget, ProviderAdapter):
    """OpenAI Responses API mit Streaming: flache Werkzeugdefinitionen, Ergebnisse als ``function_call_output``.

    Der Systemtext geht als ``instructions`` mit; die Eingabe-Items unterliegen derselben Kontextgrenze wie
    die übrigen Adapter. Zusammenfassungen des Denkens werden nur angefordert, wenn die Fähigkeitsprüfung
    des Profils sie bestätigt hat (``reasoning_summary``); manche Modelle lehnen die Angabe ab.
    """

    provider = "openai_responses"
    streams = True
    _RESULT_FIELD, _RESULT_KIND, _RESULT_KEY = "type", "function_call_output", "output"

    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: Optional[str],
        endpoint_path: Optional[str],
        reasoning_summary: bool = False,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.model = self.model_name or "gpt-4o"
        base = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.url = f"{base}/{(endpoint_path or '/responses').lstrip('/')}"
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.reasoning_summary = reasoning_summary
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
        self._start_conversation(
            self.system_prompt, self.history, self.prompt, system_in_messages=False
        )

    @property
    def input(self) -> list[dict]:
        return self.messages

    async def _complete_once(self, client, turn_index, tool_choice):
        self._fit_messages()
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": self.system_prompt,
            "input": self.messages,
            "tools": self.wire_tools,
            "stream": True,
        }
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if cfg.openai_model_supports_custom_temperature(self.model):
            payload["temperature"] = self.temperature
        if self.reasoning_summary:
            payload["reasoning"] = {"summary": "auto"}

        completed: Optional[dict] = None
        reasoning: list[str] = []
        async with admitted_stream(
            client, self.url, kind="chat", json=payload, headers=self.headers
        ) as resp:
            await raise_for_stream_status(resp, self.provider)
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                kind = event.get("type")
                delta = event.get("delta")
                if kind == "response.output_text.delta" and isinstance(delta, str) and delta:
                    yield delta
                elif kind == "response.reasoning_summary_text.delta" and isinstance(delta, str):
                    reasoning.append(delta)
                    yield Reasoning(delta)
                elif kind == "response.reasoning_summary_part.done" and reasoning:
                    reasoning.append("\n\n")
                elif kind in ("response.completed", "response.incomplete"):
                    completed = event.get("response") or {}
                elif kind in ("response.failed", "error"):
                    error = (event.get("response") or {}).get("error") or event
                    raise ResponsesStreamError(
                        f"Responses API meldet einen Fehler: {error.get('message') or error}"
                    )
        if completed is None:
            raise ResponsesStreamError("Der Responses-Stream endete ohne Abschlussereignis.")

        items = completed.get("output") or []
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
        usage = completed.get("usage") or {}
        incomplete = (completed.get("incomplete_details") or {}).get("reason")
        self._calibrate(usage.get("input_tokens"))
        # Die Ausgabe-Items sind der Assistenten-Zug, auf den sich die Ergebnisse beziehen.
        yield ModelTurn(
            text="".join(texts) or completed.get("output_text", ""),
            tool_calls=calls,
            raw=items,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            finish_reason="length"
            if incomplete == "max_output_tokens"
            else completed.get("status"),
            reasoning="".join(reasoning).strip(),
        )

    def add_tool_results(self, calls, results, turn):
        if turn is not None:
            self.messages.extend(turn.raw)
        else:
            self.messages.extend(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                }
                for call in calls
            )
        self.messages.extend(
            {"type": "function_call_output", "call_id": call.id, "output": result}
            for call, result in zip(calls, results)
        )

    def add_user_text(self, text):
        self.messages.append({"role": "user", "content": text})


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
