"""
Sync-Flow- und Orphan-Schutz-Tests für den FolderWatch-Connector (AP-8).

Der reguläre Sync-Flow (Delta-Erkennung, Orphan-Cleanup bei wirklich entfernten
Dateien) hatte bisher keinen dedizierten Test -- test_connectors.py prüft nur
die Registry. Der zweite Test bildet die beim Entkernen verlorene
"Orphan-Schutz bei unvollständigem Scan"-Testabdeckung nach (ehemals
test_incomplete_scan_safety.py, hing an Autodesk/Dalux): FolderConnector.sync()
bricht die Orphan-Bereinigung ab, wenn _current_scan leer ist (siehe
`if not self._current_scan: return` in connectors/folder.py) -- das schützt
vor stillem Datenverlust, wenn ein Netzlaufwerk kurzzeitig nicht gemountet war
und der Scan deshalb fälschlich "leer" statt "fehlgeschlagen" zurückkam.
"""

import pytest
from sqlalchemy import text
from unittest.mock import patch, AsyncMock

from db import SessionLocal
from models.database import KnowledgeSource, SourceScanFile, DocumentChunk
from connectors.folder import FolderConnector


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_source(db_session, tmp_path):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "folder-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "folder-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(
        name="Test Folder",
        type="FolderWatch",
        url=str(tmp_path),
        project_id=project_id,
        team_id=team_id,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    yield source

    db_session.query(SourceScanFile).filter(SourceScanFile.source_id == source.id).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.delete(source)
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


@pytest.mark.anyio
async def test_folder_connector_sync_flow_and_orphan_cleanup(db_session, test_source, tmp_path):
    file_a = tmp_path / "a.txt"
    file_a.write_text("Hello from folder file A")
    # Eine zweite Datei bleibt bestehen, damit _current_scan im zweiten Sync nicht
    # leer wird -- sonst greift FolderConnector.sync()s "leerer Scan = evtl.
    # fehlgeschlagen"-Schutz (siehe Test unten) und die Orphan-Bereinigung würde
    # bewusst übersprungen, statt die entfernte Datei a.txt zu bereinigen.
    file_b = tmp_path / "b.txt"
    file_b.write_text("Hello from folder file B")

    mock_get_embedding = AsyncMock(return_value=[0.1] * 1024)

    connector = FolderConnector(test_source.id)
    connector.source = test_source
    with patch("connectors.base.get_embedding", mock_get_embedding):
        docs = [doc async for doc in connector.fetch_documents()]
        await connector.sync()

    assert len(docs) == 2
    assert {doc["title"] for doc in docs} == {"a.txt", "b.txt"}

    records = db_session.query(SourceScanFile).filter(SourceScanFile.source_id == test_source.id).all()
    assert {r.file_path for r in records} == {str(file_a), str(file_b)}

    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == str(file_a)
    ).all()
    assert len(chunks) == 1

    # db_session steht nach den obigen SELECTs in einer offenen (nur lesenden)
    # Transaktion -- ohne Commit blockiert das den nächsten sync() weiter unten,
    # der über eine ANDERE Session dieselbe knowledge_sources-Zeile committet
    # (per pg_locks verifiziert: db_session hält die Zeile, bis sie committet/
    # rollbacked wird, und der zweite sync() wartet dann auf genau diese Sperre).
    db_session.commit()

    # a.txt wird entfernt (b.txt bleibt) -- der nächste Sync muss a.txts Chunk +
    # SourceScanFile als Orphan bereinigen, b.txt aber unangetastet lassen.
    file_a.unlink()
    connector2 = FolderConnector(test_source.id)
    connector2.source = test_source
    with patch("connectors.base.get_embedding", mock_get_embedding):
        docs2 = [doc async for doc in connector2.fetch_documents()]
        await connector2.sync()

    assert docs2 == []
    db_session.expire_all()
    remaining = db_session.query(SourceScanFile).filter(SourceScanFile.source_id == test_source.id).all()
    assert {r.file_path for r in remaining} == {str(file_b)}
    assert db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == str(file_a)
    ).count() == 0
    assert db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == str(file_b)
    ).count() == 1


@pytest.mark.anyio
async def test_folder_connector_skips_orphan_cleanup_on_empty_scan(db_session, test_source, tmp_path):
    """Ein leerer/fehlgeschlagener Scan (_current_scan bleibt {}) darf bestehende
    SourceScanFile-/DocumentChunk-Einträge NICHT als Orphans löschen -- sonst würde
    ein kurzzeitig nicht erreichbares Netzlaufwerk den kompletten Index leeren."""
    stale_path = str(tmp_path / "report.txt")

    db_session.add(SourceScanFile(
        source_id=test_source.id, file_path=stale_path, content_hash="abc123",
    ))
    db_session.add(DocumentChunk(
        project_id=test_source.project_id,
        source_id=test_source.id,
        file_path=stale_path,
        content="alter Inhalt",
        start_line=1,
        end_line=1,
        embedding=[0.0] * 1024,
    ))
    db_session.commit()

    connector = FolderConnector(test_source.id)
    connector.source = test_source

    async def empty_scan():
        connector._current_scan = {}
        return
        yield  # pragma: no cover -- macht die Funktion zum Async-Generator

    connector.fetch_documents = empty_scan

    mock_get_embedding = AsyncMock(return_value=[0.1] * 1024)
    with patch("connectors.base.get_embedding", mock_get_embedding):
        await connector.sync()

    db_session.expire_all()
    assert db_session.query(SourceScanFile).filter(
        SourceScanFile.source_id == test_source.id, SourceScanFile.file_path == stale_path
    ).count() == 1
    assert db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == stale_path
    ).count() == 1
