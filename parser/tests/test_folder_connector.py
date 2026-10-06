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
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"
        ),
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

    records = (
        db_session.query(SourceScanFile).filter(SourceScanFile.source_id == test_source.id).all()
    )
    assert {r.file_path for r in records} == {str(file_a), str(file_b)}

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == str(file_a))
        .all()
    )
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
    remaining = (
        db_session.query(SourceScanFile).filter(SourceScanFile.source_id == test_source.id).all()
    )
    assert {r.file_path for r in remaining} == {str(file_b)}
    assert (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == str(file_a))
        .count()
        == 0
    )
    assert (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == str(file_b))
        .count()
        == 1
    )


@pytest.mark.anyio
async def test_folder_connector_skips_orphan_cleanup_on_empty_scan(
    db_session, test_source, tmp_path
):
    """Ein leerer/fehlgeschlagener Scan (_current_scan bleibt {}) darf bestehende
    SourceScanFile-/DocumentChunk-Einträge NICHT als Orphans löschen -- sonst würde
    ein kurzzeitig nicht erreichbares Netzlaufwerk den kompletten Index leeren."""
    stale_path = str(tmp_path / "report.txt")

    db_session.add(
        SourceScanFile(
            source_id=test_source.id,
            file_path=stale_path,
            content_hash="abc123",
        )
    )
    db_session.add(
        DocumentChunk(
            project_id=test_source.project_id,
            source_id=test_source.id,
            file_path=stale_path,
            content="alter Inhalt",
            start_line=1,
            end_line=1,
            embedding=[0.0] * 1024,
        )
    )
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
    assert (
        db_session.query(SourceScanFile)
        .filter(SourceScanFile.source_id == test_source.id, SourceScanFile.file_path == stale_path)
        .count()
        == 1
    )
    assert (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == stale_path)
        .count()
        == 1
    )


@pytest.mark.anyio
async def test_folder_connector_logs_exception_type_when_a_chunk_fails_to_embed(
    db_session, test_source, tmp_path
):
    """
    Regression: on_embed_error logged "Embedding-Fehler für 'X': " with
    nothing after the colon when the underlying exception's str() is empty
    (e.g. httpx.TimeoutException) -- no clue what actually failed. Unlike
    GitConnector (which retries a failed batch chunk-by-chunk), BaseConnector-
    derived connectors like this one have no fallback beneath this single
    embed attempt: a chunk that fails here is genuinely dropped.
    """
    file_a = tmp_path / "a.txt"
    file_a.write_text("Hello from folder file A")

    connector = FolderConnector(test_source.id)
    connector.source = test_source
    with patch("connectors.base.get_embedding", AsyncMock(side_effect=Exception())):
        await connector.sync()

    db_session.refresh(test_source)
    assert "Embedding-Fehler für 'a.txt': Exception:" in test_source.sync_log

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == str(file_a))
        .all()
    )
    assert len(chunks) == 0


# --- Scan-Sicherheit, Kodierung, Vorfilter, Ausschlüsse --------------------------------------

import os  # noqa: E402

from connectors import folder as folder_module  # noqa: E402
from connectors.textio import decode_text  # noqa: E402


def test_decode_text_handles_utf8_bom_utf16_cp1252_and_latin1():
    assert decode_text("Größe €".encode("utf-8")) == "Größe €"
    assert decode_text(b"\xef\xbb\xbfStra\xc3\x9fe") == "Straße"
    assert decode_text("Müller".encode("utf-16")) == "Müller"
    # Windows-Export: Umlaute und Euro-Zeichen waren mit errors="ignore" verloren
    assert decode_text("Müller zahlt 5 €".encode("cp1252")) == "Müller zahlt 5 €"
    # 0x81 ist in cp1252 undefiniert -> Latin-1 statt Fehler
    assert decode_text(b"a\x81b") == "a\x81b"


def test_scan_skips_system_and_temp_files_and_hidden_folders(tmp_path):
    (tmp_path / "ok.txt").write_text("a")
    (tmp_path / "~$ok.docx").write_text("lock")
    (tmp_path / "Thumbs.db").write_text("x")
    (tmp_path / "notizen.tmp").write_text("x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.txt").write_text("x")
    (tmp_path / "@eaDir").mkdir()
    (tmp_path / "@eaDir" / "vorschau.txt").write_text("x")
    (tmp_path / "unterordner").mkdir()
    (tmp_path / "unterordner" / "b.md").write_text("b")

    scan = folder_module._scan_folder(str(tmp_path))
    assert {os.path.basename(p) for p in scan.files} == {"ok.txt", "b.md"}
    assert scan.complete is True


def test_scan_reuses_the_stored_hash_when_size_and_mtime_are_unchanged(tmp_path, monkeypatch):
    path = tmp_path / "gross.txt"
    path.write_text("inhalt")
    first = folder_module._scan_folder(str(tmp_path))
    size, mtime_ns = first.stats[str(path)]

    def must_not_read(_path):
        raise AssertionError("unveraenderte Datei darf nicht erneut gelesen werden")

    monkeypatch.setattr(folder_module, "_md5", must_not_read)
    second = folder_module._scan_folder(str(tmp_path), {str(path): (size, mtime_ns, first.files[str(path)])})
    assert second.files == first.files and second.reused_hashes == 1

    # Geänderte Größe -> wird neu gelesen
    monkeypatch.setattr(folder_module, "_md5", lambda _p: "neu")
    third = folder_module._scan_folder(str(tmp_path), {str(path): (size + 1, mtime_ns, "alt")})
    assert third.files[str(path)] == "neu"


def test_unreadable_directory_makes_the_scan_incomplete(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("a")
    real_walk = os.walk

    def flaky_walk(top, onerror=None, **kwargs):
        yield from real_walk(top, onerror=onerror, **kwargs)
        if onerror:
            onerror(PermissionError(13, "Permission denied", str(tmp_path / "gesperrt")))

    monkeypatch.setattr(folder_module.os, "walk", flaky_walk)
    scan = folder_module._scan_folder(str(tmp_path))
    assert scan.complete is False and "gesperrt" in scan.errors[0]
    assert len(scan.files) == 1


def test_files_over_the_size_limit_are_reported_not_indexed(tmp_path, monkeypatch):
    (tmp_path / "klein.txt").write_text("a")
    (tmp_path / "riesig.txt").write_text("x" * 100)
    monkeypatch.setattr(folder_module, "MAX_FILE_BYTES", 10)
    scan = folder_module._scan_folder(str(tmp_path))
    assert {os.path.basename(p) for p in scan.files} == {"klein.txt"}
    assert [os.path.basename(p) for p in scan.too_large] == ["riesig.txt"]


@pytest.mark.anyio
async def test_incomplete_scan_does_not_delete_the_index_of_files_it_could_not_see(db_session, test_source, tmp_path, monkeypatch):
    keep = tmp_path / "bleibt.txt"
    keep.write_text("bleibt")
    gone = tmp_path / "unlesbar.txt"
    gone.write_text("war da")
    mock_embedding = AsyncMock(return_value=[0.1] * 1024)

    first = FolderConnector(test_source.id)
    first.source = test_source
    with patch("connectors.base.get_embedding", mock_embedding):
        [doc async for doc in first.fetch_documents()]
        await first.sync()
    db_session.commit()

    # Zweiter Lauf: unlesbar.txt fehlt im Scan, weil ein Verzeichnis nicht lesbar war.
    real_walk = os.walk

    def flaky_walk(top, onerror=None, **kwargs):
        for root, dirs, files in real_walk(top, onerror=onerror, **kwargs):
            yield root, dirs, [f for f in files if f != "unlesbar.txt"]
        if onerror:
            onerror(PermissionError(13, "Permission denied", str(tmp_path / "unlesbar.txt")))

    monkeypatch.setattr(folder_module.os, "walk", flaky_walk)
    second = FolderConnector(test_source.id)
    second.source = test_source
    with patch("connectors.base.get_embedding", mock_embedding):
        [doc async for doc in second.fetch_documents()]
        await second.sync()

    db_session.expire_all()
    paths = {r.file_path for r in db_session.query(SourceScanFile).filter(SourceScanFile.source_id == test_source.id)}
    assert str(gone) in paths and str(keep) in paths
    chunk_paths = {c.file_path for c in db_session.query(DocumentChunk).filter(DocumentChunk.source_id == test_source.id)}
    assert str(gone) in chunk_paths
    stored = db_session.query(SourceScanFile).filter(SourceScanFile.file_path == str(keep)).one()
    assert stored.size_bytes == len("bleibt") and stored.mtime_ns


# --- Gebündelte Embeddings und Fehlerbehandlung ----------------------------------------------

@pytest.mark.anyio
async def test_all_chunks_of_a_document_are_embedded_in_one_batch_call(db_session, test_source, tmp_path):
    (tmp_path / "lang.txt").write_text("\n".join(f"Zeile {i} " + "x" * 80 for i in range(400)))
    calls = []

    async def batch(texts, model=None, retries=3):
        calls.append(len(texts))
        return [[0.1] * 1024 for _ in texts]

    connector = FolderConnector(test_source.id)
    with patch("connectors.base.get_embeddings_batch", side_effect=batch):
        await connector.sync()

    assert len(calls) == 1 and calls[0] > 1
    db_session.expire_all()
    assert db_session.query(DocumentChunk).filter(DocumentChunk.source_id == test_source.id).count() == calls[0]


@pytest.mark.anyio
async def test_a_failed_embedding_is_reported_not_swallowed_and_retried_next_time(db_session, test_source, tmp_path):
    (tmp_path / "a.txt").write_text("Inhalt A")
    failing = AsyncMock(side_effect=RuntimeError("Embedding-Dienst down"))

    connector = FolderConnector(test_source.id)
    with patch("connectors.base.get_embedding", failing):
        await connector.sync()

    db_session.expire_all()
    source = db_session.get(KnowledgeSource, test_source.id)
    assert source.sync_status == "error" and "nicht eingebettet" in source.last_error
    assert source.last_synced_at is None  # Zeitstempel bleibt stehen
    # Kein halbes Dokument im Index und die Datei gilt nicht als erledigt.
    assert db_session.query(DocumentChunk).filter(DocumentChunk.source_id == test_source.id).count() == 0
    assert db_session.query(SourceScanFile).filter(SourceScanFile.source_id == test_source.id).count() == 0

    db_session.commit()
    healthy = AsyncMock(return_value=[0.1] * 1024)
    again = FolderConnector(test_source.id)
    with patch("connectors.base.get_embedding", healthy):
        await again.sync()
    db_session.expire_all()
    assert db_session.get(KnowledgeSource, test_source.id).sync_status == "completed"
    assert db_session.query(DocumentChunk).filter(DocumentChunk.source_id == test_source.id).count() == 1
