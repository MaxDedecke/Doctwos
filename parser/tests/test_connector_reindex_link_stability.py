"""
Regressionstest für Re-Index-Stabilität von EntityDocLink über den
Connector-Pfad (BaseConnector._process_document) -- also Git, Confluence,
Jira, FolderWatch und WebDAV/SharePoint.

Pendant zu test_document_reindex_link_stability.py, das nur den lokalen
Upload-Pfad (tasks/document.py) abdeckt. Beide Pfade riefen vor der
Extraktion von reindex_chunks_preserving_links (parser/chunk_reindex.py)
unterschiedlichen Code auf -- der Connector-Pfad hatte kein
Fingerprint-Rewire und war damit über Auto-Sync (unbeaufsichtigt, gegen
das CDE des Kunden) weiterhin verwundbar, obwohl der lokale Pfad bereits
gefixt war.
"""

import pytest
from sqlalchemy import text
from unittest.mock import patch, AsyncMock

from db import SessionLocal
from models.database import CodeEntity, DocumentChunk, EntityDocLink, KnowledgeSource
from connectors.webdav import WebdavConnector


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
        {"name": "connector-reindex-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "connector-reindex-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(
        name="Test WebDAV",
        type="WebDAV",
        url="https://dav.example.invalid/remote.php/dav/",
        token="webdav_token_123",
        project_id=project_id,
        team_id=team_id,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    entity = CodeEntity(
        project_id=project_id,
        source_id=source.id,
        file_path="XAAOA.cbl",
        name="XAAOA",
        type="program",
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


def _doc(content: str) -> dict:
    return {
        "title": "Betriebshandbuch-XAAOA.pdf",
        "content": content,
        "url": None,
        "source_type": "WebDAV",
        "storage_key": "file-1",
        "extra_meta": {},
    }


@pytest.mark.anyio
async def test_connector_reindex_rewires_approved_link_when_content_unchanged(db_session, test_source):
    source, project_id, entity = test_source
    connector = WebdavConnector(source.id)
    connector.source = source

    mock_get_embedding = AsyncMock(return_value=[0.1] * 1024)
    with patch("connectors.base.get_embedding", mock_get_embedding):
        await connector._process_document(_doc("Dies ist ein stabiler Testabsatz zum Programm XAAOA."))
    connector.db.commit()

    first_chunk = db_session.execute(
        text("SELECT id FROM document_chunks WHERE source_id = :sid AND file_path = 'file-1'"),
        {"sid": source.id},
    ).scalar_one()

    link = EntityDocLink(
        project_id=project_id,
        entity_id=entity.id,
        chunk_id=first_chunk,
        doc_title="Betriebshandbuch-XAAOA.pdf",
        status="approved",
        link_type="semantic",
        created_by="auto",
    )
    db_session.add(link)
    db_session.commit()
    link_id = link.id

    # Re-Sync mit unverändertem Inhalt -- der Connector-Pfad löscht+erzeugt
    # neu wie jeder Delta-Sync, der Chunk bekommt also zwingend eine neue ID.
    with patch("connectors.base.get_embedding", mock_get_embedding):
        await connector._process_document(_doc("Dies ist ein stabiler Testabsatz zum Programm XAAOA."))
    connector.db.commit()

    second_chunk = db_session.execute(
        text("SELECT id FROM document_chunks WHERE source_id = :sid AND file_path = 'file-1'"),
        {"sid": source.id},
    ).scalar_one()
    assert second_chunk != first_chunk

    db_session.expire_all()
    refreshed = db_session.query(EntityDocLink).filter(EntityDocLink.id == link_id).one()
    assert refreshed.chunk_id == second_chunk
    assert refreshed.status == "approved"


@pytest.mark.anyio
async def test_connector_reindex_resets_approved_link_to_pending_when_content_changes(db_session, test_source):
    source, project_id, entity = test_source
    connector = WebdavConnector(source.id)
    connector.source = source

    mock_get_embedding = AsyncMock(return_value=[0.1] * 1024)
    with patch("connectors.base.get_embedding", mock_get_embedding):
        await connector._process_document(_doc("Handbuch Abschnitt 4.2: Abbruch bei Rueckgabecode 8."))
    connector.db.commit()

    first_chunk_id = db_session.execute(
        text("SELECT id FROM document_chunks WHERE source_id = :sid AND file_path = 'file-1'"),
        {"sid": source.id},
    ).scalar_one()

    link = EntityDocLink(
        project_id=project_id,
        entity_id=entity.id,
        chunk_id=first_chunk_id,
        doc_title="Betriebshandbuch-XAAOA.pdf",
        status="approved",
        score=0.9,
        link_type="semantic",
        created_by="auto",
    )
    db_session.add(link)
    db_session.commit()
    link_id = link.id

    # Revision B: Inhalt der Passage aendert sich tatsaechlich (neue Fassung
    # des Dokuments kommt über den Auto-Sync herein).
    with patch("connectors.base.get_embedding", mock_get_embedding):
        await connector._process_document(_doc("Handbuch Abschnitt 4.2: Abbruch bei Rueckgabecode 12."))
    connector.db.commit()

    db_session.expire_all()
    refreshed = db_session.query(EntityDocLink).filter(EntityDocLink.id == link_id).one()
    assert refreshed.chunk_id is None
    assert refreshed.status == "pending"
    assert refreshed.context is not None and "erneute Prüfung" in refreshed.context
