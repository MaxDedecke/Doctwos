"""
backend/services/think_filter.py
================================
Denkabschnitte (``<think>…</think>``) aus Modellausgaben lösen, gestreamt und am Ende.

Server ohne Reasoning-Parser (vLLM ohne ``--reasoning-parser``, ältere Ollama-Versionen) liefern das
Denken von Qwen3 als ``<think>…</think>`` im Antworttext. Füllt das Chat-Template das öffnende Tag
selbst vor, kommt nur das schließende an; dann ist alles davor Denken. Live-Filter und abschließende
Bereinigung müssen dieselbe Regel anwenden, sonst zeigt die Live-Anzeige etwas anderes als die fertige
Antwort. Das Denken wird nicht verworfen, sondern getrennt gesammelt (Reasoning-Kanal).
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
    """Trennt ``<think>…</think>`` von gestreamtem Text, auch wenn ein Tag über eine Stückgrenze läuft.

    ``feed()`` liefert den sichtbaren Text, ``take_reasoning()`` das seither erkannte Denken. Ein
    schließendes Tag ohne öffnendes macht bereits ausgegebenen Text nachträglich zu Denken; ``take_reset()``
    meldet das einmal, der Aufrufer verwirft dann die bisherige Live-Anzeige.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False
        self._shown: list[str] = []
        self._reasoning: list[str] = []
        self._reset = False

    def feed(self, piece: str) -> str:
        self._buffer += piece
        out: list[str] = []
        while self._buffer:
            if self._inside:
                index = self._buffer.find(_CLOSE)
                if index < 0:
                    cut = len(self._buffer) - _partial_tag_length(self._buffer, _CLOSE)
                    self._reasoning.append(self._buffer[:cut])
                    self._buffer = self._buffer[cut:]
                    break
                self._reasoning.append(self._buffer[:index])
                self._buffer = self._buffer[index + len(_CLOSE) :]
                self._inside = False
                continue
            open_at, close_at = self._buffer.find(_OPEN), self._buffer.find(_CLOSE)
            if close_at >= 0 and (open_at < 0 or close_at < open_at):
                self._reset = self._reset or any(self._shown)
                self._reasoning.append("".join(self._shown + out) + self._buffer[:close_at])
                self._shown, out = [], []
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
        self._shown.append(text)
        return text

    def take_reset(self) -> bool:
        """True genau einmal, nachdem bereits ausgegebener Text sich als Denken herausgestellt hat."""
        reset, self._reset = self._reset, False
        return reset

    def take_reasoning(self) -> str:
        """Seit dem letzten Abruf erkanntes Denken."""
        reasoning, self._reasoning = "".join(self._reasoning), []
        return reasoning

    def flush(self) -> str:
        rest, self._buffer = self._buffer, ""
        if self._inside:
            self._reasoning.append(rest)
            return ""
        return rest


# Je Modellzug gespeichertes Denken; der Rest ist für die Nachvollziehbarkeit entbehrlich und bläht die Nachricht.
MAX_REASONING_STEP_CHARS = 8000


def reasoning_step(turn: int, text: str) -> dict | None:
    """Arbeitsschritt für das Denken eines Modellzugs, gekürzt; None, wenn es keins gab."""
    text = text.strip()
    if not text:
        return None
    if len(text) > MAX_REASONING_STEP_CHARS:
        text = text[:MAX_REASONING_STEP_CHARS].rstrip() + " […]"
    return {"type": "reasoning", "turn": turn, "content": text}
