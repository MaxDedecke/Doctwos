"""Begründung eines Doku-Vorschlags: getrennt nach Abschnitt und Code, Zitate gegen ihre Quelle geprüft.

Link-Lauf (parser/tasks/link_builder.py) und Einzelprüfung im Link-Manager (backend/api/entity_links.py)
lassen das Modell dieselben Felder füllen. Ein Reviewer prüft gegen den angezeigten Abschnitt; Belege, die nur
im Codekontext stehen, lasen sich sonst wie Inhalt des Dokuments (Syncope, Lauf 158).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Für ein JSON-Objekt je Kandidat; das umgebende Format (Objekt oder Array) legt der Aufrufer fest.
REASON_FIELDS_PROMPT = (
    '"section": "1-2 Sätze: was der Abschnitt selbst über die Entity sagt. Nur, was im Inhalt des Abschnitts '
    'steht; Namen in `Backticks` genau so, wie sie dort stehen.", '
    '"code": "1 Satz: welche Stelle im Codekontext der Entity dazu passt. Namen in `Backticks` genau so, wie sie '
    'im Codekontext stehen.", '
    '"uncertain": "1 Satz: was ungewiss bleibt."'
)
REASON_RULE_PROMPT = "Schreibe dem Abschnitt nichts zu, was nur im Codekontext steht. Keine bloße Ähnlichkeitsaussage."
UNVERIFIED_NOTE = "[Zitat nicht in der genannten Quelle gefunden: {quotes}] "

_QUOTE = re.compile(r"`([^`\n]{2,120})`")
_QUOTE_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_$-]{2,}")
_QUOTE_FILLER = {"class", "extends", "implements", "interface", "new", "public", "return", "void"}


def unverified_quotes(text: str, sources: Iterable[str | None]) -> list[str]:
    """Namen in Backticks, deren Bestandteile in keiner Quelle stehen (``foo()`` passt zu ``foo(Bar.java:12)``)."""
    haystack = "\n".join(source for source in sources if source).casefold()
    missing = []
    for quote in _QUOTE.findall(text or ""):
        parts = [p for p in _QUOTE_PART.findall(quote) if p.casefold() not in _QUOTE_FILLER]
        if parts and not all(part.casefold() in haystack for part in parts):
            missing.append(quote)
    return list(dict.fromkeys(missing))


def compose_reason(
    review: dict, section_sources: Iterable[str | None], code_sources: Iterable[str | None]
) -> str:
    """Setzt die Felder zur angezeigten Begründung zusammen; nicht belegte Zitate stehen vorn als Hinweis.

    Antworten im früheren Format (nur ``reason``) werden gegen Abschnitt und Code zusammen geprüft.
    """
    section_sources, code_sources = list(section_sources), list(code_sources)
    section, code, uncertain = (
        str(review.get(key) or "").strip() for key in ("section", "code", "uncertain")
    )
    if section or code:
        reason = "\n".join(
            f"{label}: {text}"
            for label, text in (
                ("Im Abschnitt", section),
                ("Im Code", code),
                ("Ungewiss", uncertain),
            )
            if text
        )
        # „Ungewiss“ nennt oft gerade, was fehlt („kein `x`-Feld“), und wird deshalb nicht geprüft.
        missing = unverified_quotes(section, section_sources) + unverified_quotes(
            code, code_sources
        )
    else:
        reason = str(review.get("reason") or "").strip()
        missing = unverified_quotes(reason, section_sources + code_sources)
    missing = list(dict.fromkeys(missing))
    if missing:
        reason = UNVERIFIED_NOTE.format(quotes=", ".join(f"`{q}`" for q in missing)) + reason
    return reason
