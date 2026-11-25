"""
backend/services/chat_export.py
===============================
Export einer Chat-Sitzung als Markdown: Fragen, Antworten, Quellen und Anhangnamen in Gesprächsreihenfolge.

Arbeitsschritte, Denken und Telemetrie bleiben draußen; der Export soll weitergegeben werden können. Antworten
tragen Modell und Modus, damit klar ist, woher eine Aussage stammt.
"""

import re
from typing import Optional

from sqlalchemy.orm import Session

from codena_models.database import ChatMessage, ChatSession


def _source_line(source: dict) -> Optional[str]:
    file = source.get("file")
    if not file:
        return None
    lines = [line for line in (source.get("lines") or []) if line]
    if not lines:
        return f"- `{file}`"
    start, end = lines[0], lines[-1]
    return f"- `{file}:{start}`" if start == end else f"- `{file}:{start}-{end}`"


def export_markdown(db: Session, session: ChatSession) -> str:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    created = session.created_at.strftime("%d.%m.%Y %H:%M") if session.created_at else ""
    parts = [f"# {session.title or 'Codena-Chat'}", ""]
    meta = [created, session.project.name if session.project else None]
    if any(meta):
        parts += [" · ".join(item for item in meta if item), ""]
    for message in messages:
        metadata = message.metadata_json or {}
        if message.role == "user":
            parts += ["## Frage", "", message.content or ""]
            names = [
                item.get("name") for item in metadata.get("attachments") or [] if item.get("name")
            ]
            if names:
                parts += ["", "Anhänge: " + ", ".join(f"`{name}`" for name in names)]
        else:
            label = " · ".join(
                item
                for item in (metadata.get("model"), metadata.get("chat_mode"))
                if isinstance(item, str) and item
            )
            parts += [f"## Antwort ({label})" if label else "## Antwort", "", message.content or ""]
            sources = [line for line in map(_source_line, message.sources_json or []) if line]
            if sources:
                parts += ["", "**Quellen**", "", *sources]
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def export_filename(session: ChatSession) -> str:
    slug = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß_-]+", "-", session.title or "chat").strip("-")[:60] or "chat"
    return f"codena-{slug}.md"
