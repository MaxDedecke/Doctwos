"""
Regressionstest für Re-Index-Stabilität von EntityDocLink (Dokumentseite).

Vor dem Fix: process_local_document_async löscht bei jedem Re-Index alle
DocumentChunk-Zeilen der Quelle und legt sie mit neuen IDs neu an. Das setzt
EntityDocLink.chunk_id (ON DELETE SET NULL) auf NULL, lässt status="approved"
aber unangetastet -- ein freigegebener Link zeigt danach auf nichts, ohne
Fehler oder Log.

Fix: vor dem Löschen wird pro betroffenem Link ein Content-Fingerprint des
alten Chunks genommen. Findet sich nach dem Re-Index ein neuer Chunk mit
identischem Fingerprint (Inhalt unverändert), wird der Link umgehängt und
behält seinen Status. Ändert sich der Inhalt, fällt ein "approved"-Link auf
"pending" zurück (erneute Prüfung), statt still auf einen toten chunk_id zu
zeigen.
"""

import os
import tempfile

import pytest
from sqlalchemy import text

from db import SessionLocal
from models.database import CodeEntity, DocumentChunk, EntityDocLink, KnowledgeSource
from tasks.document import process_local_document_async

from conftest import requires_ollama


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
        {"name": "doc-reindex-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "doc-reindex-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(
        name="Test-Dokument",
        type="local_document",
        project_id=project_id,
        team_id=team_id,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    entity = CodeEntity(
        project_id=project_id,
        source_id=source.id,
        file_path="dummy.py",
        name="EntityUnterBeobachtung",
        type="generic",
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)

    yield source, project_id, entity

    db_session.query(EntityDocLink).filter(EntityDocLink.project_id == project_id).delete()
    db_session.query(CodeEntity).filter(CodeEntity.project_id == project_id).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.delete(source)
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


def _write_temp_txt(content: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(content)
        return f.name


@pytest.mark.anyio
@requires_ollama
async def test_reindex_rewires_approved_link_when_content_unchanged(db_session, test_source):
    source, project_id, entity = test_source
    file_path = _write_temp_txt("Dies ist ein stabiler Testabsatz fuer Brandschutz.")

    try:
        await process_local_document_async(source.id, file_path)
        first_chunk = db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).one()
        first_chunk_id = first_chunk.id

        link = EntityDocLink(
            project_id=project_id,
            entity_id=entity.id,
            chunk_id=first_chunk_id,
            doc_title="Test-Dokument",
            status="approved",
        )
        db_session.add(link)
        db_session.commit()
        link_id = link.id

        # Re-index mit unverändertem Inhalt -- Chunk bekommt eine neue ID
        await process_local_document_async(source.id, file_path)

        db_session.expire_all()
        second_chunk = db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).one()
        assert second_chunk.id != first_chunk_id

        refreshed = db_session.query(EntityDocLink).filter(EntityDocLink.id == link_id).one()
        assert refreshed.chunk_id == second_chunk.id
        assert refreshed.status == "approved"
    finally:
        os.unlink(file_path)


@pytest.mark.anyio
@requires_ollama
async def test_reindex_resets_approved_link_to_pending_when_content_changes(db_session, test_source):
    source, project_id, entity = test_source
    file_path = _write_temp_txt("Brandschutznachweis Abschnitt 4.2: Feuerwiderstand EI 90.")

    try:
        await process_local_document_async(source.id, file_path)
        first_chunk = db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).one()

        link = EntityDocLink(
            project_id=project_id,
            entity_id=entity.id,
            chunk_id=first_chunk.id,
            doc_title="Test-Dokument",
            status="approved",
            score=0.9,
        )
        db_session.add(link)
        db_session.commit()
        link_id = link.id

        # Revision B: Inhalt der Passage aendert sich tatsaechlich
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("Brandschutznachweis Abschnitt 4.2: Feuerwiderstand EI 30.")

        await process_local_document_async(source.id, file_path)

        db_session.expire_all()
        refreshed = db_session.query(EntityDocLink).filter(EntityDocLink.id == link_id).one()
        assert refreshed.chunk_id is None
        assert refreshed.status == "pending"
        assert refreshed.context is not None and "erneute Prüfung" in refreshed.context
    finally:
        os.unlink(file_path)
