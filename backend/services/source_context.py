"""
backend/services/source_context.py
====================================
Baut den "Fachwissen"-Block aus KnowledgeSource.context_note für den
System-Prompt (siehe api/chat.py).

Anders als RAG-Retrieval (DocumentChunk, embedding-basiert) wird die Notiz
nicht durchsucht/gerankt, sondern immer komplett mitgeschickt, sobald ihre
Quelle im aktuellen Chat-Scope liegt:
    - Chat auf eine Quelle eingeschränkt (source_id)  → nur deren Notiz
    - Projektweiter Chat (project_id, keine source_id) → alle Notizen des
      Projekts, mit Quellenname als Label, bis zum Gesamtbudget
    - Weder noch (globaler Chat ohne Projekt)          → kein Block

Die Notiz kommt vom Anlegenden der Quelle selbst (kein extern gescrapter
Content) und wird deshalb im System-Prompt als vertrauenswürdiger Text
behandelt, nicht in <untrusted_...>-Tags gewrappt.
"""

from sqlalchemy.orm import Session

from models.database import KnowledgeSource

# Deckel für die Summe aller Notizen bei projektweitem Chat — verhindert, dass
# der System-Prompt mit wachsender Quellenzahl unkontrolliert wächst. Einzelne
# Notizen sind bereits serverseitig auf SOURCE_CONTEXT_NOTE_MAX_CHARS begrenzt
# (siehe api/knowledge_sources.py); dieses Budget deckelt zusätzlich die Summe.
DEFAULT_TOTAL_BUDGET_CHARS = 6000


def build_source_context_block(
    db: Session,
    *,
    project_id: int | None,
    source_id: int | None,
    total_budget_chars: int = DEFAULT_TOTAL_BUDGET_CHARS,
) -> str:
    if source_id:
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
        if not source or not source.context_note:
            return ""
        return _format_block([source])

    if not project_id:
        return ""

    sources = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.project_id == project_id, KnowledgeSource.context_note.isnot(None))
        .order_by(KnowledgeSource.id)
        .all()
    )
    if not sources:
        return ""

    picked = []
    remaining = total_budget_chars
    for source in sources:
        note_len = len(source.context_note or "")
        if note_len > remaining:
            break
        picked.append(source)
        remaining -= note_len
    if not picked:
        return ""
    return _format_block(picked)


def _format_block(sources: list[KnowledgeSource]) -> str:
    entries = "\n\n".join(
        f"### {source.name} ({source.type})\n{source.context_note}" for source in sources
    )
    return (
        "\n\n### Fachwissen/Begriffe zu den verbundenen Wissensquellen:\n"
        "Vom Nutzer hinterlegter Hintergrund zu einzelnen Wissensquellen — nutze ihn, "
        "um kundenspezifische Fachbegriffe/Konventionen richtig einzuordnen.\n\n"
        f"{entries}"
    )
