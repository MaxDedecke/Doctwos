"""Language-neutral graph expansion for chat retrieval (F-043).

Vektor-Treffer werden über ihre Datei/Zeilen einem möglichst spezifischen
CodeEntity zugeordnet. Danach ergänzen wir Definition-Chunks von COPY-Zielen
und Aufrufern. Das harte Zeichenbudget ist absichtlich unabhängig vom Modell;
vier Zeichen pro Token sind eine konservative, deterministische Näherung.
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.database import CodeEdge, CodeEntity, DocumentChunk


DEFAULT_GRAPH_TOKEN_BUDGET = 1800

# Only semantic/code relationships can add useful source context.  Keeping the
# allowlist explicit avoids pulling in bookkeeping edges such as DEFINES while
# allowing Java's open parser edge taxonomy without another language branch.
RETRIEVAL_EDGE_TYPES = frozenset(
    {
        "COPY",
        "CALL",
        "CALLS",
        "INSTANTIATES",
        "EXTENDS",
        "IMPLEMENTS",
        "USES_TYPE",
        "READS",
        "WRITES",
    }
)


def expand_chunks_with_graph(
    db: Session,
    chunks: list[DocumentChunk],
    *,
    token_budget: int = DEFAULT_GRAPH_TOKEN_BUDGET,
) -> list[DocumentChunk]:
    if not chunks or token_budget <= 0:
        return chunks

    picked = list(chunks)
    picked_ids = {chunk.id for chunk in chunks}
    entity_ids: set[int] = set()

    for chunk in chunks:
        query = db.query(CodeEntity).filter(
            CodeEntity.project_id == chunk.project_id,
            CodeEntity.file_path == chunk.file_path,
            CodeEntity.source_id == chunk.source_id,
        )
        if chunk.start_line is not None and chunk.end_line is not None:
            query = query.filter(
                CodeEntity.start_line <= chunk.end_line,
                CodeEntity.end_line >= chunk.start_line,
            ).order_by(
                (CodeEntity.end_line - CodeEntity.start_line).asc(),
                CodeEntity.id.asc(),
            )
        # Alle überlappenden Hierarchieebenen sind relevant: ein Paragraph-Chunk
        # gehört zugleich zum Paragraphen und zum Programm. CALL-Kanten hängen am
        # Programm, COPY kann je nach Fundstelle an einer tieferen Entity hängen.
        entity_ids.update(entity.id for entity in query.all())

    if not entity_ids:
        return picked

    # F-043: one-hop semantic neighbors.  Both directions matter for Java:
    # a class is useful together with its parent and its subclasses, while a
    # method is useful with both callers and callees.
    edges = (
        db.query(CodeEdge)
        .filter(
            CodeEdge.type.in_(RETRIEVAL_EDGE_TYPES),
            CodeEdge.resolution == "resolved",
            or_(CodeEdge.src_entity_id.in_(entity_ids), CodeEdge.dst_entity_id.in_(entity_ids)),
        )
        .all()
    )
    neighbor_ids = {
        edge.dst_entity_id if edge.src_entity_id in entity_ids else edge.src_entity_id
        for edge in edges
    }
    neighbor_ids.discard(None)
    if not neighbor_ids:
        return picked

    neighbors = (
        db.query(CodeEntity).filter(CodeEntity.id.in_(neighbor_ids)).order_by(CodeEntity.id).all()
    )
    remaining_chars = token_budget * 4
    for entity in neighbors:
        definitions = db.query(DocumentChunk).filter(
            DocumentChunk.project_id == entity.project_id,
            DocumentChunk.source_id == entity.source_id,
            DocumentChunk.file_path == entity.file_path,
        )
        if entity.start_line is not None and entity.end_line is not None:
            definitions = definitions.filter(
                DocumentChunk.start_line <= entity.end_line,
                DocumentChunk.end_line >= entity.start_line,
            )
        for chunk in definitions.order_by(DocumentChunk.start_line, DocumentChunk.id).all():
            if chunk.id in picked_ids:
                continue
            size = len(chunk.content or "")
            if size > remaining_chars:
                continue
            picked.append(chunk)
            picked_ids.add(chunk.id)
            remaining_chars -= size
            if remaining_chars <= 0:
                return picked
    return picked
