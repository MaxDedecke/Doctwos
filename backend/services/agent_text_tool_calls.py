"""Werkzeugaufrufe, die das Modell als Text statt als strukturierten Aufruf geschrieben hat.

qwen3-coder schreibt seine Aufrufe als ``<function=NAME><parameter=KEY>WERT</parameter></function>``, Qwen3 und
Hermes-Modelle als ``<tool_call>{"name": ..., "arguments": {...}}</tool_call>``. Der Server erkennt sie nur, wenn
das Modell das Format genau trifft; fehlt etwa das öffnende ``<tool_call>``, kommt der Aufruf als Antworttext an
(Benchmark 17.11.: etwa jede 15. bis 20. Coder-Sitzung). Ohne diese Erkennung sähe der Nutzer das Markup als
Antwort.

Erkannt wird nur, was eindeutig ist: Jeder Aufruf nennt ein angebotenes Werkzeug, und seine Parameter lassen sich
lesen. Sonst bleibt der Text, wie er ist.
"""

from __future__ import annotations

import json
import re
from typing import Iterable, Optional

from services.agent_providers import ToolCall

_MARKERS = ("<function=", "<tool_call>")
_FUNCTION = re.compile(r"<function=([A-Za-z0-9_.-]+)>(.*?)(?:</function>|\Z)", re.S)
_PARAMETER = re.compile(
    r"<parameter=([A-Za-z0-9_.-]+)>\s*(.*?)\s*(?:</parameter>|(?=<parameter=)|\Z)", re.S
)
_JSON_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*(?:</tool_call>|\Z)", re.S)


def tool_names(tools: Iterable[dict]) -> set[str]:
    names = set()
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        name = (tool.get("function") or {}).get("name") or tool.get("name")
        if name:
            names.add(name)
    return names


def _value(raw: str):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def recover(text: str, offered: set[str], turn_index: int) -> Optional[tuple[str, list[ToolCall]]]:
    """(Text vor dem Aufruf, Aufrufe) oder None, wenn der Text keinen eindeutigen Werkzeugaufruf enthält."""
    start = min((i for i in (text.find(m) for m in _MARKERS) if i >= 0), default=-1)
    if start < 0 or not offered:
        return None
    body = text[start:]
    calls: list[ToolCall] = []
    for name, inner in _FUNCTION.findall(body):
        arguments = {key: _value(value) for key, value in _PARAMETER.findall(inner)}
        calls.append(ToolCall(f"tc-{turn_index}-text-{len(calls)}", name, arguments))
    if not calls:
        for raw in _JSON_CALL.findall(body):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return None
            arguments = data.get("arguments", data.get("parameters", {}))
            if isinstance(arguments, str):
                arguments = _value(arguments)
            if not isinstance(arguments, dict):
                return None
            calls.append(
                ToolCall(f"tc-{turn_index}-text-{len(calls)}", data.get("name", ""), arguments)
            )
    if not calls or any(call.name not in offered for call in calls):
        return None
    return text[:start].rstrip(), calls


class MarkupFilter:
    """Hält gestreamten Text ab dem Beginn eines Aufruf-Markups zurück, damit der Nutzer es nicht sieht."""

    def __init__(self) -> None:
        self._pending = ""
        self.stopped = False

    def feed(self, piece: str) -> str:
        if self.stopped:
            return ""
        text = self._pending + piece
        hits = [i for i in (text.find(m) for m in _MARKERS) if i >= 0]
        if hits:
            self.stopped = True
            self._pending = ""
            return text[: min(hits)]
        # Ein Rest, der der Anfang eines Markers sein kann, wartet auf das nächste Stück.
        keep = 0
        for marker in _MARKERS:
            for size in range(min(len(marker) - 1, len(text)), 0, -1):
                if text.endswith(marker[:size]):
                    keep = max(keep, size)
                    break
        self._pending = text[len(text) - keep :] if keep else ""
        return text[: len(text) - keep]

    def flush(self) -> str:
        rest, self._pending = ("" if self.stopped else self._pending), ""
        return rest
