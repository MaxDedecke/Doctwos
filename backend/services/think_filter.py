"""
backend/services/think_filter.py
================================
Denkabschnitte (``<think>…</think>``) aus Modellausgaben entfernen, gestreamt und am Ende.

Server ohne Reasoning-Parser (vLLM ohne ``--reasoning-parser``, ältere Ollama-Versionen) liefern das
Denken von Qwen3 als ``<think>…</think>`` im Antworttext. Füllt das Chat-Template das öffnende Tag
selbst vor, kommt nur das schließende an; dann ist alles davor Denken. Live-Filter und abschließende
Bereinigung müssen dieselbe Regel anwenden, sonst zeigt die Live-Anzeige etwas anderes als die fertige
Antwort.
"""

import re

_OPEN, _CLOSE = "<think>", "</think>"
_THINK_BLOCK_RE = re.compile(r"<think>.*?(?:</think>|\Z)", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Antworttext ohne Denkabschnitte."""
    if "think>" not in text:
        return text
    text = _THINK_BLOCK_RE.sub("", text)
    if _CLOSE in text:
        text = text.rsplit(_CLOSE, 1)[1]
    return text.lstrip()


def _partial_tag_length(buffer: str, *tags: str) -> int:
    """Länge eines möglichen Tag-Anfangs am Pufferende, der auf das nächste Stück warten muss."""
    return max(
        (n for tag in tags for n in range(len(tag) - 1, 0, -1) if buffer.endswith(tag[:n])),
        default=0,
    )


class ThinkFilter:
    """Entfernt ``<think>…</think>`` aus gestreamtem Text, auch wenn ein Tag über eine Stückgrenze läuft.

    Ein schließendes Tag ohne öffnendes macht bereits ausgegebenen Text nachträglich zu Denken.
    ``take_reset()`` meldet das einmal; der Aufrufer verwirft dann die bisherige Live-Anzeige.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False
        self._emitted = False
        self._reset = False

    def feed(self, piece: str) -> str:
        self._buffer += piece
        out: list[str] = []
        while self._buffer:
            if self._inside:
                index = self._buffer.find(_CLOSE)
                if index < 0:
                    keep = _partial_tag_length(self._buffer, _CLOSE)
                    self._buffer = self._buffer[len(self._buffer) - keep :]
                    break
                self._buffer = self._buffer[index + len(_CLOSE) :]
                self._inside = False
                continue
            open_at, close_at = self._buffer.find(_OPEN), self._buffer.find(_CLOSE)
            if close_at >= 0 and (open_at < 0 or close_at < open_at):
                out.clear()
                self._reset = self._reset or self._emitted
                self._emitted = False
                self._buffer = self._buffer[close_at + len(_CLOSE) :]
                continue
            if open_at >= 0:
                out.append(self._buffer[:open_at])
                self._buffer = self._buffer[open_at + len(_OPEN) :]
                self._inside = True
                continue
            cut = len(self._buffer) - _partial_tag_length(self._buffer, _OPEN, _CLOSE)
            out.append(self._buffer[:cut])
            self._buffer = self._buffer[cut:]
            break
        text = "".join(out)
        self._emitted = self._emitted or bool(text)
        return text

    def take_reset(self) -> bool:
        """True genau einmal, nachdem bereits ausgegebener Text sich als Denken herausgestellt hat."""
        reset, self._reset = self._reset, False
        return reset

    def flush(self) -> str:
        rest, self._buffer = self._buffer, ""
        return "" if self._inside else rest
