"""
backend/services/chat_followups.py
==================================
Folgevorschläge zu einer Antwort: drei kurze Anschlussfragen vom Chatmodell, an der Antwort gespeichert.

Die Vorschläge kosten einen kleinen Modellaufruf; sie entstehen deshalb erst auf Anfrage der Oberfläche
(nach der jüngsten Antwort) und werden je Antwort nur einmal erzeugt. Sie sind Formulierungshilfen,
keine Aussagen über den Bestand.
"""

import re
from typing import Optional

from sqlalchemy.orm import Session

import core.config as cfg
from doctus_models.database import ChatMessage
from services.profile_capabilities import requests_reasoning_summary
from services.standard_chat import stream_standard_rag_events

MAX_SUGGESTIONS = 3
MAX_SUGGESTION_CHARS = 140
_EXCERPT_CHARS = 2500
_SYSTEM = (
    "Du schlägst Anschlussfragen für ein Gespräch mit dem Code-Assistenten Doctus vor. Antworte nur mit "
    "genau drei kurzen Fragen, eine je Zeile, ohne Nummern oder Einleitung, in der Sprache der Frage. Die "
    "Fragen sollen das Thema vertiefen (Aufrufer, Datenherkunft, betroffene Programme, Tests) und dürfen "
    "keine Fakten behaupten."
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def parse_suggestions(text: str) -> list[str]:
    """Bis zu drei Fragen aus der Modellantwort, ohne Aufzählungszeichen und Dubletten."""
    seen: set[str] = set()
    suggestions: list[str] = []
    for line in text.splitlines():
        question = _BULLET_RE.sub("", line).strip().strip('"„“')
        if len(question) < 8 or question.lower() in seen:
            continue
        seen.add(question.lower())
        suggestions.append(question[:MAX_SUGGESTION_CHARS])
        if len(suggestions) == MAX_SUGGESTIONS:
            break
    return suggestions


def _question_before(db: Session, answer: ChatMessage) -> Optional[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == answer.session_id,
            ChatMessage.role == "user",
            ChatMessage.id < answer.id,
        )
        .order_by(ChatMessage.id.desc())
        .first()
    )


async def follow_up_suggestions(db: Session, answer: ChatMessage, profile) -> list[str]:
    """Gespeicherte oder neu erzeugte Folgevorschläge; ein Modellfehler ergibt eine leere Liste."""
    stored = (answer.metadata_json or {}).get("suggestions")
    if isinstance(stored, list):
        return stored
    question = _question_before(db, answer)
    prompt = (
        f"Frage: {(question.content if question else '')[:800]}\n\n"
        f"Antwort (Auszug): {(answer.content or '')[:_EXCERPT_CHARS]}\n\n"
        "Drei Anschlussfragen:"
    )
    text = ""
    async for event in stream_standard_rag_events(
        provider=profile.provider.lower(),
        model=profile.llm_model,
        api_key=profile.llm_api_key,
        base_url=profile.llm_base_url,
        temperature=cfg.DEFAULT_CHAT_TEMPERATURE,
        system_prompt=_SYSTEM,
        history=[],
        prompt=prompt,
        protocol=profile.protocol,
        path=profile.llm_path,
        context_length=profile.llm_context_length,
        reasoning_summary=requests_reasoning_summary(profile),
    ):
        if event["type"] == "error":
            return []
        if event["type"] == "answer":
            text = event["content"]
    suggestions = parse_suggestions(text)
    answer.metadata_json = {**(answer.metadata_json or {}), "suggestions": suggestions}
    db.commit()
    return suggestions
