"""Einträge der Web-Quellen eines Projekts als eigene Knoten der Übersicht (Issues, Seiten).

Ohne Verknüpfung zum Code tauchte ein Ticket bisher gar nicht im Graphen auf. Jeder indexierte
Eintrag wird ein Knoten, auch ohne Kante; ``web_entry`` hält ihn bei „nur verknüpfte“ sichtbar.
Anhänge bleiben außen vor, sie gehören zu ihrer Seite.
"""

from typing import Callable

from sqlalchemy.orm import Session, load_only

from doctus_models.database import DocumentChunk, KnowledgeSource, User
from services.source_access import source_visible
from services.web_documents import is_web_source

# Obergrenze je Übersicht; die Knotenkappung der Übersicht greift zusätzlich.
WEB_ENTRY_LIMIT = 2000


def append_web_entries(
    db: Session, user: User, project_id: int, nodes: dict[str, dict], doc_node: Callable
) -> int:
    sources = [
        source
        for source in db.query(KnowledgeSource)
        .filter(KnowledgeSource.project_id == project_id)
        .order_by(KnowledgeSource.id)
        if is_web_source(source.type) and source_visible(db, user, source.id)
    ]
    added = 0
    for source in sources:
        # Ein Abschnitt je Eintrag genügt: Die Knoten-ID hängt am Eintrag, nicht am Abschnitt.
        chunks = (
            db.query(DocumentChunk)
            .options(
                load_only(
                    DocumentChunk.id,
                    DocumentChunk.project_id,
                    DocumentChunk.source_id,
                    DocumentChunk.file_path,
                    DocumentChunk.metadata_json,
                )
            )
            .filter(DocumentChunk.source_id == source.id)
            .distinct(DocumentChunk.file_path)
            .order_by(DocumentChunk.file_path, DocumentChunk.id)
            .limit(WEB_ENTRY_LIMIT - added)
        )
        for chunk in chunks:
            meta = chunk.metadata_json or {}
            if meta.get("attachment_filename"):
                continue
            node = doc_node(
                meta.get("title") or chunk.file_path, source.type, meta.get("url"), chunk
            )
            if node["id"] in nodes:
                nodes[node["id"]]["web_entry"] = True
                continue
            node["web_entry"] = True
            nodes[node["id"]] = node
            added += 1
        if added >= WEB_ENTRY_LIMIT:
            break
    return added
