"""
Regressionstest gegen die Fingerprint-Kollision in reindex_chunks_preserving_links:
zwei Chunks mit identischem (whitespace-normalisiertem) Inhalt -- wiederkehrende
Standardklauseln, Kopf-/Fußzeilen, "Anforderung gemäß Art. 24 BayBO" in mehreren
Abschnitten -- dürfen bei Re-Index NICHT dazu führen, dass ein approved-Link an
die falsche Passage umgehängt wird (Dict last-wins). Mehrdeutigkeit muss auf
"pending" fallen, nicht auf einen geratenen Treffer.
"""

import pytest

from db import SessionLocal
from models.database import CodeEntity, DocumentChunk, EntityDocLink, KnowledgeSource
from chunk_reindex import reindex_chunks_preserving_links
from sqlalchemy import text


DUPLICATE_TEXT = "Anforderung gemäß Art. 24 BayBO: Rettungswege müssen stets freigehalten werden."


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_source(db_session):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "collision-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "collision-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(name="Test-Dokument", type="local_document", project_id=project_id, team_id=team_id)
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    entity_a = CodeEntity(project_id=project_id, source_id=source.id, file_path="a.py", name="EntityA", type="generic")
    entity_b = CodeEntity(project_id=project_id, source_id=source.id, file_path="b.py", name="EntityB", type="generic")
    db_session.add_all([entity_a, entity_b])
    db_session.commit()
    db_session.refresh(entity_a)
    db_session.refresh(entity_b)

    yield source, project_id, entity_a, entity_b

    db_session.query(EntityDocLink).filter(EntityDocLink.project_id == project_id).delete()
    db_session.query(CodeEntity).filter(CodeEntity.project_id == project_id).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.delete(source)
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


def _build_chunk(source):
    def build(chunk, embedding):
        return DocumentChunk(
            project_id=source.project_id,
            source_id=source.id,
            file_path="doc.txt",
            content=chunk["content"],
            start_line=chunk["start_line"],
            end_line=chunk["end_line"],
            embedding=embedding,
            metadata_json={},
        )
    return build


async def _embed(content):
    return [0.1] * 1024


@pytest.mark.anyio
async def test_duplicate_content_chunks_fall_back_to_pending_instead_of_wrong_rewire(db_session, test_source):
    source, project_id, entity_a, entity_b = test_source

    # Zwei Chunks mit exakt demselben normalisierten Inhalt -- z.B. eine
    # Klausel, die im Dokument an zwei Stellen auftaucht.
    initial_chunks = [
        {"content": DUPLICATE_TEXT, "start_line": 1, "end_line": 1},
        {"content": DUPLICATE_TEXT, "start_line": 50, "end_line": 50},
    ]
    await reindex_chunks_preserving_links(
        db_session, source_id=source.id, file_path="doc.txt", chunks=initial_chunks,
        build_chunk=_build_chunk(source), embed_content=_embed,
    )
    db_session.commit()

    chunk_ids = [row[0] for row in db_session.execute(
        text("SELECT id FROM document_chunks WHERE source_id = :sid ORDER BY id"), {"sid": source.id}
    ).all()]
    assert len(chunk_ids) == 2

    # Zwei unabhängige, jeweils schon geprüfte Links zeigen auf die zwei
    # (inhaltsgleichen) Passagen.
    link_a = EntityDocLink(project_id=project_id, entity_id=entity_a.id, chunk_id=chunk_ids[0],
                            doc_title="doc.txt", status="approved", link_type="semantic", created_by="auto")
    link_b = EntityDocLink(project_id=project_id, entity_id=entity_b.id, chunk_id=chunk_ids[1],
                            doc_title="doc.txt", status="approved", link_type="semantic", created_by="auto")
    db_session.add_all([link_a, link_b])
    db_session.commit()
    link_a_id, link_b_id = link_a.id, link_b.id

    # Re-Index mit unverändertem Inhalt -- weiterhin zwei identische Chunks.
    await reindex_chunks_preserving_links(
        db_session, source_id=source.id, file_path="doc.txt", chunks=initial_chunks,
        build_chunk=_build_chunk(source), embed_content=_embed,
    )
    db_session.commit()

    db_session.expire_all()
    refreshed_a = db_session.query(EntityDocLink).filter(EntityDocLink.id == link_a_id).one()
    refreshed_b = db_session.query(EntityDocLink).filter(EntityDocLink.id == link_b_id).one()

    # Mehrdeutig -> beide fallen sicher auf "pending" zurück, statt dass
    # last-wins beide (oder eines falsch) an dieselbe neue Chunk-ID rewired.
    for refreshed in (refreshed_a, refreshed_b):
        assert refreshed.chunk_id is None
        assert refreshed.status == "pending"
        assert "erneute Prüfung" in (refreshed.context or "")


@pytest.mark.anyio
async def test_unique_content_still_rewires_correctly_when_other_chunk_is_duplicated(db_session, test_source):
    """Kontrollfall: nur die duplizierte Passage muss auf pending fallen,
    eine eindeutige dritte Passage im selben Dokument bleibt approved+rewired."""
    source, project_id, entity_a, entity_b = test_source

    unique_text = "Individuelle Abschnittsbezeichnung, die nur einmal vorkommt."
    initial_chunks = [
        {"content": DUPLICATE_TEXT, "start_line": 1, "end_line": 1},
        {"content": DUPLICATE_TEXT, "start_line": 50, "end_line": 50},
        {"content": unique_text, "start_line": 100, "end_line": 100},
    ]
    await reindex_chunks_preserving_links(
        db_session, source_id=source.id, file_path="doc.txt", chunks=initial_chunks,
        build_chunk=_build_chunk(source), embed_content=_embed,
    )
    db_session.commit()

    all_chunks = db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).all()
    unique_chunk_id = next(c.id for c in all_chunks if c.content == unique_text)

    link_unique = EntityDocLink(project_id=project_id, entity_id=entity_a.id, chunk_id=unique_chunk_id,
                                 doc_title="doc.txt", status="approved", link_type="semantic", created_by="auto")
    db_session.add(link_unique)
    db_session.commit()
    link_unique_id = link_unique.id

    await reindex_chunks_preserving_links(
        db_session, source_id=source.id, file_path="doc.txt", chunks=initial_chunks,
        build_chunk=_build_chunk(source), embed_content=_embed,
    )
    db_session.commit()

    db_session.expire_all()
    all_chunks_after = db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).all()
    new_unique_chunk_id = next(c.id for c in all_chunks_after if c.content == unique_text)

    refreshed = db_session.query(EntityDocLink).filter(EntityDocLink.id == link_unique_id).one()
    assert refreshed.chunk_id == new_unique_chunk_id
    assert refreshed.status == "approved"
