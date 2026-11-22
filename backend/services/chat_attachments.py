"""
backend/services/chat_attachments.py
====================================
Anhänge an Chatfragen (Quelltexte, Logs, Auszüge): prüfen, verschlüsselt an der Frage speichern und begrenzt in
die Modellanfrage legen.

Anhänge sind Fremdinhalt wie abgerufene Quellen: Sie stehen in ``<untrusted_attachment>``-Blöcken, der
Sicherheitshinweis im Systemtext gilt für sie. Ihr Anteil am Kontextfenster ist begrenzt, damit Frage, Belege
und Antwort Platz behalten; was nicht passt, wird sichtbar gekürzt. Wiederholen und Bearbeiten nehmen die
gespeicherten Anhänge der Frage, nicht die des Clients.
"""

import json
from typing import Optional
from xml.sax.saxutils import quoteattr

from services.attachment_text import readable
from services.chat_errors import ChatInvalid

MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_CHARS = 200_000
MAX_NAME_CHARS = 200
# Anteil des Kontextfensters für alle Anhänge zusammen; ohne Profilangabe gilt ein Fenster von 32.768 Tokens.
ATTACHMENT_SHARE = 0.3
CHARS_PER_TOKEN = 3.5
DEFAULT_CONTEXT_TOKENS = 32768
_CUT_NOTE = "\n[… Anhang gekürzt, damit er ins Kontextfenster des Modells passt]"


def validate(attachments: Optional[list]) -> list[dict]:
    """Bereinigte Anhänge aus der Anfrage; Fehler bei zu vielen oder zu großen."""
    if not attachments:
        return []
    if len(attachments) > MAX_ATTACHMENTS:
        raise ChatInvalid(f"Höchstens {MAX_ATTACHMENTS} Anhänge je Frage")
    cleaned = []
    for item in attachments:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        name = str(data.get("name") or "").strip()[:MAX_NAME_CHARS]
        content = str(data.get("content") or "")
        if not name or not content.strip():
            raise ChatInvalid("Ein Anhang braucht Namen und Inhalt")
        if len(content) > MAX_ATTACHMENT_CHARS:
            raise ChatInvalid(f"Anhang '{name}' ist größer als {MAX_ATTACHMENT_CHARS} Zeichen")
        cleaned.append({"name": name, "content": content})
    return cleaned


def dump(attachments: list[dict]) -> Optional[str]:
    return json.dumps(attachments, ensure_ascii=False) if attachments else None


def load(stored: Optional[str]) -> list[dict]:
    if not stored:
        return []
    try:
        items = json.loads(stored)
    except ValueError:
        return []
    return [item for item in items if isinstance(item, dict) and item.get("name")]


def summary(attachments: list[dict]) -> list[dict]:
    """Was in den unverschlüsselten Metadaten stehen darf: Name und Größe, kein Inhalt."""
    return [{"name": item["name"], "chars": len(item["content"])} for item in attachments]


def prompt_block(attachments: list[dict], context_length: Optional[int]) -> tuple[str, list[dict]]:
    """Anhänge als gekennzeichnete Fremdinhalte, gemeinsam auf ihren Anteil am Kontextfenster begrenzt.

    HTML wird vorher zu Text (``attachment_text``). Kurze Anhänge geben ungenutzten Platz an längere ab. Zurück
    kommen der Block und je gekürztem Anhang Name, gezeigte und gesamte Zeichen (für den Hinweis im Chat).
    """
    if not attachments:
        return "", []
    budget = int((context_length or DEFAULT_CONTEXT_TOKENS) * CHARS_PER_TOKEN * ATTACHMENT_SHARE)
    texts = [readable(item["name"], item["content"]) for item in attachments]
    shares: dict[int, int] = {}
    remaining = budget
    order = sorted(range(len(texts)), key=lambda index: len(texts[index]))
    for position, index in enumerate(order):
        fair = max(500, remaining // (len(order) - position))
        shares[index] = min(len(texts[index]), fair)
        remaining = max(0, remaining - shares[index])
    blocks, trimmed = [], []
    for index, item in enumerate(attachments):
        content = texts[index]
        if len(content) > shares[index]:
            trimmed.append({"name": item["name"], "shown": shares[index], "total": len(content)})
            content = content[: max(0, shares[index] - len(_CUT_NOTE))] + _CUT_NOTE
        blocks.append(
            f"<untrusted_attachment name={quoteattr(item['name'])}>\n{content}\n</untrusted_attachment>"
        )
    return "Vom Nutzer angehängt:\n" + "\n".join(blocks) + "\n\n", trimmed
