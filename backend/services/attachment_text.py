"""
backend/services/attachment_text.py
===================================
Lesbarer Text aus HTML-Anhängen, bevor sie fürs Modell gekürzt werden.

Eine gespeicherte Webseite besteht oft zum größten Teil aus Skripten und Stilen (der Benchmark-Bericht: 85.000
Zeichen, davon 4.500 Text). Kürzt man sie roh, bleibt nur der Kopf mit CSS übrig. Hier fallen Skripte, Stile
und Markup weg; Absätze, Überschriften, Listen und Tabellenzeilen bleiben als Zeilen erhalten. Reine
Standardbibliothek, keine zusätzliche Abhängigkeit.
"""

import json
import re
from html import unescape
from html.parser import HTMLParser

_SKIP = {"script", "style", "noscript", "svg", "template", "head"}
_BLOCK = {
    "p",
    "div",
    "section",
    "article",
    "header",
    "footer",
    "main",
    "aside",
    "nav",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ul",
    "ol",
    "tr",
    "table",
    "thead",
    "tbody",
    "pre",
    "blockquote",
    "figure",
    "figcaption",
    "details",
    "summary",
    "dt",
    "dd",
    "title",
}
_CELL = {"td", "th"}
_HTML_START = re.compile(r"^\s*(<!doctype\s+html|<html[\s>])", re.IGNORECASE)


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.scripts: list[str] = []
        self._skip_depth = 0
        self._in_script = False
        self._title = False

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self._in_script = True
        if tag in _SKIP and tag != "head":
            self._skip_depth += 1
        elif tag == "title":
            self._title = True
        elif tag in _BLOCK:
            self.parts.append("\n")
        elif tag in _CELL:
            self.parts.append(" | ")
        if tag in {"h1", "h2", "h3", "h4"}:
            self.parts.append("## ")
        elif tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False
        if tag in _SKIP and tag != "head":
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._title = False
            self.parts.append("\n")
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_script:
            self.scripts.append(data)
        elif self._skip_depth == 0:
            self.parts.append(data)


def is_html(name: str, content: str) -> bool:
    return name.lower().endswith((".html", ".htm", ".xhtml")) or bool(
        _HTML_START.match(content[:200])
    )


# Daten, die eine Seite per Skript darstellt (``const DATA = {...}``, ``window.x = [...]``, JSON-Skripte).
_DATA_ASSIGNMENT = re.compile(
    r"(?:\b(?:const|let|var)\s+|\bwindow\.)([A-Za-z_$][\w$]*)\s*=\s*(?=[\[{])"
)


def _embedded_data(scripts: list[str]) -> list[str]:
    """Daten-Literale aus Skripten als kompaktes JSON; Programmcode bleibt draußen."""
    decoder = json.JSONDecoder()
    found = []
    for script in scripts:
        stripped = script.strip()
        if stripped[:1] in "[{":
            candidates = [("", 0, stripped)]
        else:
            candidates = [(m.group(1), m.end(), script) for m in _DATA_ASSIGNMENT.finditer(script)]
        for name, start, source in candidates:
            try:
                value, _ = decoder.raw_decode(source, start)
            except ValueError:
                continue
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            found.append(f"{name} = {text}" if name else text)
    return found


def html_to_text(content: str) -> str:
    collector = _TextCollector()
    collector.feed(content)
    collector.close()
    data = _embedded_data(collector.scripts)
    text = unescape("".join(collector.parts))
    lines = [re.sub(r"[ \t ]+", " ", line).strip(" |") for line in text.splitlines()]
    text = "\n".join(line.strip() for line in lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if data:
        text += "\n\n## Eingebettete Daten der Seite (aus Skripten)\n" + "\n".join(data)
    return text


def readable(name: str, content: str) -> str:
    """Der Text, den das Modell vom Anhang sehen soll; Nicht-HTML bleibt unverändert."""
    return html_to_text(content) if is_html(name, content) else content
