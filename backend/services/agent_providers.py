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
from doctus_models.inference_admission import admitted_stream
from core.inference_errors import ContextWindowExceeded, raise_for_stream_status
from core.llm_providers import is_self_hosted_openai
from services.think_filter import ThinkFilter, strip_thinking

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
    # Getrennt geliefertes Denken des Zugs (siehe Reasoning); leer, wenn der Server keins liefert.
    reasoning: str = ""


@dataclass
class Reasoning:
    """Stück Denken, das der Server getrennt von der Antwort liefert.

    Quellen: Ollamas ``message.thinking``, ``reasoning_content``/``reasoning`` im Chat-Completions-Stream,
    Zusammenfassungen der Responses API und ``<think>``-Abschnitte im Text. Es ist, was der Anbieter
    freigibt, kein Versprechen auf die vollständige interne Herleitung.
    """

    text: str


def _parse_arguments(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw if raw is not None else {}
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        return raw


def _schema(tool: dict) -> dict:
    return tool.get("inputSchema", {"type": "object", "properties": {}})


# Annahme für Zeichen je Token, bis der Server echte Zahlen meldet (gemessen an Qwen3: rund 4).
_DEFAULT_CHARS_PER_TOKEN = 3.5
_TRIMMED_TOOL_RESULT = (
    "[Älteres Werkzeugergebnis entfernt, damit das Gespräch ins Kontextfenster des Modells passt. "
    "Bei Bedarf das Werkzeug erneut aufrufen.]"
)
_CONTEXT_CUT_NOTE = (
    "\n[… abgerufener Kontext gekürzt, damit Frage und Belege ins Kontextfenster passen]"
)
_RESULT_CUT_NOTE = "\n[… Werkzeugergebnis gekürzt, damit es ins Kontextfenster passt]"
_CONTEXT_BLOCK_RE = re.compile(r"(<untrusted_context>\n)(.*)(\n</untrusted_context>)", re.DOTALL)
_MIN_TOOL_RESULT_CHARS = 400
# Gekürzte Teile: Schlüssel für Anzeige und Ereignisse, Text für das Log.
_CUT_LABELS = {
    "older_tool_results": "älteres Werkzeugergebnis",
    "history": "Verlauf",
    "retrieved_context": "abgerufener Kontext",
    "tool_results": "Werkzeugergebnis",
}
# So oft wird nach einer Ablehnung "Anfrage zu groß" mit der Tokenzahl des Servers nachgekürzt.
_OVERFLOW_RETRIES = 2


def _wire_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False))


class _ChatMessageBudget:
    """Hält ein Gespräch aus ``role``/``content``-Nachrichten unter dem Kontextfenster des Profils.

    Ohne diese Grenze kürzt der Server: Ollama entfernte ganze Nachrichten von vorn und behielt nur
    Systemtext und Gesprächsende, sodass das Modell ein Werkzeugergebnis ohne die Frage sah; vLLM und
    llama.cpp lehnen die Anfrage ab. Systemtext, Werkzeugschemata und die Frage bleiben deshalb immer
    stehen. Gekürzt wird in dieser Reihenfolge, bis es passt: ältere Werkzeugergebnisse (nicht das erste,
    das vorab geladene Belegpaket, und nicht das jüngste), Verlauf, abgerufener Kontext in der Frage,
    zuletzt die verbliebenen Werkzeugergebnisse.
    """

    context_length: Optional[int]
    wire_tools: list[dict]
    _chars_per_token: float = _DEFAULT_CHARS_PER_TOKEN
    _sent_chars: int = 0
    # Außerhalb der Nachrichtenliste gesendeter Text (Responses: ``instructions``).
    _fixed_chars: int = 0
    # Woran ein Werkzeugergebnis erkannt wird und unter welchem Schlüssel sein Text steht.
    _RESULT_FIELD, _RESULT_KIND, _RESULT_KEY = "role", "tool", "content"

    def _start_conversation(
        self, system_prompt: str, history: list[dict], prompt: str, system_in_messages: bool = True
    ) -> None:
        self.messages: list[dict] = []
        if system_prompt and system_in_messages:
            self.messages.append({"role": "system", "content": system_prompt})
        elif system_prompt:
            self._fixed_chars = len(system_prompt)
        self._history_messages = [{"role": m["role"], "content": m["content"]} for m in history]
        self.messages.extend(self._history_messages)
        self._prompt_message = {"role": "user", "content": prompt}
        self.messages.append(self._prompt_message)
        self._context_cut: set[str] = set()

    def take_context_cut(self) -> list[str]:
        """Seit dem letzten Abruf gekürzte Teile; die Schleife meldet sie als eigenes Ereignis."""
        cut, self._context_cut = sorted(self._context_cut), set()
        return cut

    def _fit_messages(self, tools_sent: bool = True) -> bool:
        """Kürzt das Gespräch auf das Fenster; True, wenn dabei etwas entfernt wurde."""
        tools_size = _wire_size(self.wire_tools) if tools_sent else 0

        def size() -> int:
            return self._fixed_chars + tools_size + sum(_wire_size(m) for m in self.messages)

        key = self._RESULT_KEY

        if not self.context_length:
            self._sent_chars = size()
            return False
        reserve = max(1500, self.context_length // 5)  # Antwort und Denken
        budget = int((self.context_length - reserve) * self._chars_per_token)
        cut: list[str] = []

        tool_messages = [m for m in self.messages if m.get(self._RESULT_FIELD) == self._RESULT_KIND]
        for message in tool_messages[1:-1]:
            if size() <= budget:
                break
            if len(message.get(key) or "") > len(_TRIMMED_TOOL_RESULT):
                message[key] = _TRIMMED_TOOL_RESULT
                cut.append("older_tool_results")

        while size() > budget and self._history_messages:
            oldest = self._history_messages.pop(0)
            self.messages[:] = [m for m in self.messages if m is not oldest]
            cut.append("history")

        excess = size() - budget
        if excess > 0:
            match = _CONTEXT_BLOCK_RE.search(self._prompt_message["content"])
            if match and match.group(2) and not match.group(2).endswith(_CONTEXT_CUT_NOTE):
                # Die JSON-Hülle maskiert Zeichen; deshalb anteilig etwas mehr abschneiden.
                keep = max(0, len(match.group(2)) - int(excess * 1.1) - len(_CONTEXT_CUT_NOTE))
                kept = match.group(2)[:keep] + _CONTEXT_CUT_NOTE
                self._prompt_message["content"] = (
                    self._prompt_message["content"][: match.start(2)]
                    + kept
                    + self._prompt_message["content"][match.end(2) :]
                )
                cut.append("retrieved_context")

        for message in sorted(tool_messages, key=lambda m: -len(m.get(key) or "")):
            excess = size() - budget
            if excess <= 0:
                break
            content = message.get(key) or ""
            keep = max(
                _MIN_TOOL_RESULT_CHARS, len(content) - int(excess * 1.1) - len(_RESULT_CUT_NOTE)
            )
            if keep < len(content):
                message[key] = content[:keep] + _RESULT_CUT_NOTE
                cut.append("tool_results")

        self._sent_chars = size()
        self._context_cut.update(cut)
        if cut or self._sent_chars > budget:
            logger.warning(
                "Gespräch am Kontextfenster (%s Tokens, geschätzt %s von %s Zeichen); gekürzt: %s",
                self.context_length,
                self._sent_chars,
                budget,
                ", ".join(sorted({_CUT_LABELS[part] for part in cut})) or "nichts mehr kürzbar",
            )
        return bool(cut)

    def _offers_tools(self, tool_choice: ToolChoice) -> bool:
        return True

    async def complete(self, client, turn_index, tool_choice):
        """Ein Modellzug; lehnt der Server die Anfrage als zu groß ab, wird nachgekürzt und wiederholt."""
        for attempt in range(_OVERFLOW_RETRIES + 1):
            try:
                async for item in self._complete_once(client, turn_index, tool_choice):
                    yield item
                return
            except ContextWindowExceeded as error:
                # Die Ablehnung kommt vor dem ersten Textstück; es wurde noch nichts ausgeliefert.
                if attempt == _OVERFLOW_RETRIES or not self._refit_after_overflow(
                    error, self._offers_tools(tool_choice)
                ):
                    raise

    def _calibrate(self, prompt_tokens: Optional[int], exact: bool = False) -> None:
        """Zeichen je Token aus der Serverangabe; ersetzt die Annahme."""
        if not (prompt_tokens and self._sent_chars):
            return
        ratio = self._sent_chars / prompt_tokens
        # Enge Grenzen für die Angabe eines erfolgreichen Zugs: Bei kleinen Anfragen bläht die JSON-Hülle
        # das Verhältnis auf. Die Ablehnung "Anfrage zu groß" nennt dagegen die volle, genaue Tokenzahl.
        self._chars_per_token = ratio * 0.97 if exact else min(4.5, max(2.5, ratio))

    def _refit_after_overflow(self, error: ContextWindowExceeded, tools_sent: bool) -> bool:
        """Kürzt mit der vom Server genannten Tokenzahl nach; False, wenn nichts mehr zu kürzen ist."""
        if error.context_tokens and (
            not self.context_length or error.context_tokens < self.context_length
        ):
            # Der Server läuft mit einem kleineren Fenster, als im Profil steht.
            self.context_length = error.context_tokens
        if error.prompt_tokens:
            self._calibrate(error.prompt_tokens, exact=True)
        else:
            self._chars_per_token *= 0.8
        return self._fit_messages(tools_sent)


def fit_chat_messages(
    system_prompt: str, history: list[dict], prompt: str, context_length: Optional[int]
) -> list[dict]:
    """Gespräch ohne Werkzeuge, auf das Kontextfenster gekürzt (Standard-Chat)."""
    conversation = _ChatMessageBudget()
    conversation.context_length = context_length
    conversation.wire_tools = []
    conversation._start_conversation(system_prompt, history, prompt)
    conversation._fit_messages(tools_sent=False)
    return conversation.messages


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

    def take_context_cut(self) -> list[str]:
        return []


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
        self._start_conversation(self.system_prompt, self.history, self.prompt)

    async def _complete_once(self, client, turn_index, tool_choice):
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
        reasoning: list[str] = []
        think_filter = ThinkFilter()
        partial_calls: dict[int, dict] = {}
        usage: dict = {}
        finish_reason: Optional[str] = None
        async with admitted_stream(
            client, self.url, kind="chat", json=payload, headers=self.headers
        ) as resp:
            await raise_for_stream_status(resp, self.provider)
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
                # vLLM mit Reasoning-Parser: ``reasoning_content`` (älter) bzw. ``reasoning``.
                thought = delta.get("reasoning_content") or delta.get("reasoning")
                if isinstance(thought, str) and thought:
                    reasoning.append(thought)
                    yield Reasoning(thought)
                if delta.get("content"):
                    raw_text += delta["content"]
                    visible = think_filter.feed(delta["content"])
                    thought = think_filter.take_reasoning()
                    if thought:
                        reasoning.append(thought)
                        yield Reasoning(thought)
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
        reasoning.append(think_filter.take_reasoning())
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
            reasoning="".join(reasoning),
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
        key = api_key or cfg.ollama_fallback_key(ollama_base_url)
        if key:
            self.headers["Authorization"] = f"Bearer {key}"
        self.model = cfg.resolve_ollama_model(self.model_name)
        self.url = f"{ollama_base_url.rstrip('/')}/{(endpoint_path or '/api/chat').lstrip('/')}"
        self.num_ctx = self.context_length or cfg.OLLAMA_NUM_CTX
        self.context_length = self.num_ctx
        self.wire_tools = _openai_wire_tools(self.tools)
        self._start_conversation(self.system_prompt, self.history, self.prompt)

    def _offers_tools(self, tool_choice):
        # Ollama kennt kein ``tool_choice``. "none" wird durch Weglassen der Werkzeuge erreicht; "required"
        # lässt sich nicht erzwingen, die Schleife verwirft eine Antwort ohne Recherche und wiederholt.
        return tool_choice != "none"

    async def _complete_once(self, client, turn_index, tool_choice):
        offer_tools = self._offers_tools(tool_choice)
        self._fit_messages(tools_sent=offer_tools)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "stream": True,
            # Ohne diesen Schalter entfernt Ollama bei Überlauf still ganze Nachrichten von vorn, zuerst
            # Verlauf und Frage. So lehnt es stattdessen ab und nennt die Tokenzahl.
            "truncate": False,
            # O-168: explizites Kontextfenster statt Ollamas stillschweigend kürzender Servervorgabe.
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        if offer_tools:
            payload["tools"] = self.wire_tools

        raw_text = ""
        reasoning: list[str] = []
        # Ältere Ollama-Versionen liefern das Denken noch im Antworttext statt in ``message.thinking``.
        think_filter = ThinkFilter()
        wire_calls: list[dict] = []
        done: dict = {}
        async with admitted_stream(
            client, self.url, kind="chat", json=payload, headers=self.headers
        ) as resp:
            await raise_for_stream_status(resp, self.provider)
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
                if isinstance(message.get("thinking"), str) and message["thinking"]:
                    reasoning.append(message["thinking"])
                    yield Reasoning(message["thinking"])
                if message.get("content"):
                    raw_text += message["content"]
                    visible = think_filter.feed(message["content"])
                    thought = think_filter.take_reasoning()
                    if thought:
                        reasoning.append(thought)
                        yield Reasoning(thought)
                    if visible:
                        yield visible
                wire_calls.extend(message.get("tool_calls") or [])
                if chunk.get("done"):
                    done = chunk
                    break
        rest = think_filter.flush()
        reasoning.append(think_filter.take_reasoning())
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
            reasoning="".join(reasoning),
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
    from services.agent_providers_hosted import (
        AnthropicAdapter,
        GeminiAdapter,
        OpenAIResponsesAdapter,
    )

    reasoning_summary = conversation.pop("reasoning_summary", False)
    if provider == "openai_responses":
        return OpenAIResponsesAdapter(
            api_key=api_key,
            base_url=base_url,
            endpoint_path=endpoint_path,
            reasoning_summary=reasoning_summary,
            **conversation,
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
