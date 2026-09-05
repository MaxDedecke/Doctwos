import os
import subprocess

import pytest
from sqlalchemy import text
from unittest.mock import patch, AsyncMock

from db import SessionLocal
from models.database import KnowledgeSource, SourceScanFile, DocumentChunk
from connectors.git import GitConnector, _looks_like_text
import git_utils


def test_looks_like_text_accepts_plain_ascii():
    assert _looks_like_text(b"IDENTIFICATION DIVISION.\nPROGRAM-ID. PROG.\n") is True


def test_looks_like_text_accepts_empty_content():
    assert _looks_like_text(b"") is True


def test_looks_like_text_rejects_invalid_utf8():
    """O-074: EBCDIC-Ziffern (0xF0-0xF4) sind ohne gültige UTF-8-Fortsetzungs-
    bytes kein decodierbarer Text."""
    assert _looks_like_text(bytes([0xF0, 0xF1, 0xF2, 0xF3, 0xF4] * 20)) is False


def test_looks_like_text_rejects_control_character_heavy_utf8():
    assert _looks_like_text(("\x01\x02\x03\x04\x05" * 100).encode("utf-8")) is False


def test_looks_like_text_tolerates_occasional_control_characters():
    """Ein paar vereinzelte Steuerzeichen in echtem Text (z. B. Form Feed in
    alten COBOL-Quellen) dürfen nicht als Datenmüll fehlklassifiziert werden."""
    text = ("IDENTIFICATION DIVISION.\nPROGRAM-ID. PROG.\n" * 20) + "\x0c"
    assert _looks_like_text(text.encode("utf-8")) is True


def _init_remote(path: str) -> None:
    subprocess.run(["git", "init", "--initial-branch=main", path], check=True, capture_output=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "test@doctus.local"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "Doctus Test"], check=True)


def _commit_file(repo: str, rel_path: str, content: str, message: str) -> None:
    full = os.path.join(repo, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", message], check=True, capture_output=True)


def _commit_binary_file(repo: str, rel_path: str, raw: bytes, message: str) -> None:
    full = os.path.join(repo, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(raw)
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", message], check=True, capture_output=True)


def _delete_file(repo: str, rel_path: str, message: str) -> None:
    subprocess.run(["git", "-C", repo, "rm", rel_path], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", message], check=True, capture_output=True)


@pytest.fixture
def git_remote(tmp_path):
    path = str(tmp_path / "remote.git")
    _init_remote(path)
    _commit_file(path, "PROG.CBL", "IDENTIFICATION DIVISION.\nPROGRAM-ID. PROG.\n", "init")
    _commit_file(path, "README.md", "# Doctus Test Repo\n", "readme")
    return path


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_source(db_session, git_remote, tmp_path, monkeypatch):
    # AP-3 legt Bare-Mirror/Worktree unter REPOS_ROOT an -- fuer den Test auf
    # ein Tempverzeichnis umbiegen, damit nichts unter /repos landet und
    # parallele Testlaeufe sich nicht in die Quere kommen.
    repos_root = str(tmp_path / "repos_root")
    monkeypatch.setattr("connectors.git.REPOS_ROOT", repos_root)

    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "git-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "git-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(
        name="Test Git",
        type="Git",
        url=git_remote,
        branch="main",
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


def _patched_sync(connector):
    return (
        patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)),
        patch("connectors.git.get_embeddings_batch", AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts])),
        patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)),
        # O-071: ohne Patch würde is_gpu_accelerated() bei jedem Testlauf einen
        # echten Ollama-Aufruf versuchen; True haelt die bisherige volle
        # EMBED_CONCURRENCY bei, damit diese Tests unveraendert bleiben.
        patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)),
    )


@pytest.mark.anyio
async def test_git_connector_initial_sync(db_session, test_source):
    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert test_source.sync_cursor and test_source.sync_cursor.get("last_commit")
    assert test_source.repo_fingerprint

    scan_files = {
        r.file_path: r for r in db_session.query(SourceScanFile).filter(
            SourceScanFile.source_id == test_source.id
        ).all()
    }
    assert set(scan_files.keys()) == {"PROG.CBL", "README.md"}
    for record in scan_files.values():
        assert len(record.content_hash) == 32

    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.source_id == test_source.id).all()
    assert len(chunks) >= 2
    languages = {c.metadata_json.get("language") for c in chunks}
    assert "cobol" in languages
    assert "text" in languages


@pytest.mark.anyio
async def test_git_connector_delta_sync_add_modify_delete(db_session, test_source, git_remote):
    connector1 = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector1)
    with p1, p2, p3, p4:
        await connector1.sync()

    # Remote aendert sich: PROG.CBL modifiziert, README.md geloescht, NEW.CBL neu
    _commit_file(git_remote, "PROG.CBL", "IDENTIFICATION DIVISION.\nPROGRAM-ID. PROG.\nMORE.\n", "update")
    _delete_file(git_remote, "README.md", "remove readme")
    _commit_file(git_remote, "NEW.CBL", "IDENTIFICATION DIVISION.\nPROGRAM-ID. NEW.\n", "add new")

    connector2 = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector2)
    with p1, p2, p3, p4:
        await connector2.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"

    scan_paths = {
        r.file_path for r in db_session.query(SourceScanFile).filter(
            SourceScanFile.source_id == test_source.id
        ).all()
    }
    assert scan_paths == {"PROG.CBL", "NEW.CBL"}

    chunk_paths = {
        c.file_path for c in db_session.query(DocumentChunk).filter(
            DocumentChunk.source_id == test_source.id
        ).all()
    }
    assert "README.md" not in chunk_paths
    assert "NEW.CBL" in chunk_paths
    assert "PROG.CBL" in chunk_paths


@pytest.mark.anyio
async def test_git_connector_force_reindex_reprocesses_unchanged_commit(db_session, test_source):
    """A forced run must parse and embed files even when the Git commit is unchanged."""
    connector = GitConnector(test_source.id)
    first_batch, first_single, first_model, first_gpu = _patched_sync(connector)
    with first_batch, first_single, first_model, first_gpu:
        await connector.sync()

    embed_batch = AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts])
    connector = GitConnector(test_source.id)
    with patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)), \
         patch("connectors.git.get_embeddings_batch", embed_batch), \
         patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)), \
         patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)):
        await connector.sync(force_reindex=True)

    assert embed_batch.await_count > 0
    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"


@pytest.mark.anyio
async def test_git_connector_resumes_via_content_hash(db_session, test_source, monkeypatch, tmp_path):
    """NF-004: eine Datei, deren Blob-SHA schon in SourceScanFile steht (z.B.
    aus einem abgebrochenen vorherigen Lauf), wird beim erneuten Sync NICHT
    neu eingebettet -- der guenstigste Resume-Mechanismus."""
    repos_root = str(tmp_path / "repos_root")
    monkeypatch.setattr("connectors.git.REPOS_ROOT", repos_root)

    fp = git_utils.compute_repo_fingerprint(test_source.url)
    bare = git_utils.ensure_bare_mirror(repos_root, fp, test_source.url)
    git_utils.fetch_branch(bare, "main")
    wt = git_utils.worktree_path(repos_root, test_source.id)
    git_utils.ensure_worktree(bare, wt, "main")
    tracked = git_utils.list_tracked_files(wt)

    db_session.add(SourceScanFile(
        source_id=test_source.id,
        file_path="PROG.CBL",
        content_hash=git_utils.blob_content_hash(tracked["PROG.CBL"]),
    ))
    db_session.commit()

    connector = GitConnector(test_source.id)
    embed_batch = AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts])
    with patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)), \
         patch("connectors.git.get_embeddings_batch", embed_batch), \
         patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)), \
         patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)):
        await connector.sync()

    embedded_titles = [call.args[0] for call in embed_batch.call_args_list]
    # PROG.CBL's einziger Chunk darf nie an get_embeddings_batch gegangen sein
    combined_texts = [t for batch in embedded_titles for t in batch]
    assert not any("PROGRAM-ID. PROG." in t for t in combined_texts)

    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id,
        DocumentChunk.file_path == "PROG.CBL",
    ).all()
    # Kein neuer Chunk fuer die uebersprungene Datei angelegt
    assert len(chunks) == 0


@pytest.mark.anyio
async def test_git_connector_shares_bare_mirror_across_sources(db_session, git_remote, tmp_path, monkeypatch):
    repos_root = str(tmp_path / "repos_root")
    monkeypatch.setattr("connectors.git.REPOS_ROOT", repos_root)

    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "git-share-team"},
    ).scalar_one()
    project_a = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "git-share-project-a", "team_id": team_id},
    ).scalar_one()
    project_b = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "git-share-project-b", "team_id": team_id},
    ).scalar_one()

    source_a = KnowledgeSource(name="A", type="Git", url=git_remote, branch="main", project_id=project_a, team_id=team_id)
    source_b = KnowledgeSource(name="B", type="Git", url=git_remote, branch="main", project_id=project_b, team_id=team_id)
    db_session.add_all([source_a, source_b])
    db_session.commit()
    db_session.refresh(source_a)
    db_session.refresh(source_b)

    try:
        for src in (source_a, source_b):
            connector = GitConnector(src.id)
            with patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)), \
                 patch("connectors.git.get_embeddings_batch", AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts])), \
                 patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)), \
                 patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)):
                await connector.sync()

        db_session.refresh(source_a)
        db_session.refresh(source_b)
        assert source_a.sync_status == "completed"
        assert source_b.sync_status == "completed"
        assert source_a.repo_fingerprint == source_b.repo_fingerprint
        bare_dir = git_utils.bare_path(repos_root, source_a.repo_fingerprint)
        assert os.path.isdir(bare_dir)
        # Genau ein Bare-Mirror, aber zwei getrennte Worktrees
        assert os.path.isdir(git_utils.worktree_path(repos_root, source_a.id))
        assert os.path.isdir(git_utils.worktree_path(repos_root, source_b.id))
    finally:
        db_session.query(SourceScanFile).filter(SourceScanFile.source_id.in_([source_a.id, source_b.id])).delete(synchronize_session=False)
        db_session.query(DocumentChunk).filter(DocumentChunk.source_id.in_([source_a.id, source_b.id])).delete(synchronize_session=False)
        db_session.delete(source_a)
        db_session.delete(source_b)
        db_session.execute(text("DELETE FROM projects WHERE id IN (:a, :b)"), {"a": project_a, "b": project_b})
        db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
        db_session.commit()


@pytest.mark.anyio
async def test_git_connector_falls_back_to_per_chunk_embedding_and_logs_a_useful_error(db_session, test_source):
    """
    Regression: a failed batch embed (e.g. httpx.TimeoutException, whose
    str() is often empty) used to log "Embedding-Fehler für 'X': " with
    nothing after the colon -- no clue what actually went wrong. The file
    itself was never lost (reindex_chunks_preserving_links falls back to
    embedding chunks one at a time when they arrive without a precomputed
    "embedding"), but the log gave no way to tell a real failure from this
    expected, self-healing fallback path.
    """
    connector = GitConnector(test_source.id)
    with patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)), \
         patch("connectors.git.get_embeddings_batch", AsyncMock(side_effect=Exception())), \
         patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)), \
         patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)):
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert "Embedding-Fehler für 'PROG.CBL': Exception:" in test_source.sync_log

    # The fallback still embedded and saved every chunk -- a failed batch
    # attempt must not silently drop a file's content.
    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id,
        DocumentChunk.file_path == "PROG.CBL",
    ).all()
    assert len(chunks) >= 1
    assert all(c.embedding is not None for c in chunks)


@pytest.mark.anyio
async def test_git_connector_logs_when_the_per_chunk_fallback_also_fails(db_session, test_source):
    """
    Regression found live against a real CardDemo (AWS mainframe demo) import:
    an EBCDIC data file's batch embed failed (logged), the per-chunk fallback
    in reindex_chunks_preserving_links then failed for every one of its
    chunks too -- and _save_document_chunks never passed on_embed_error,
    unlike connectors/base.py's equivalent. The failure was completely
    silent: the file still logged "'X' indexiert (0 Chunks)", indistinguishable
    from a genuinely empty file like .gitkeep. A customer reporting "my file
    isn't in search results" would have had nothing to go on.
    """
    connector = GitConnector(test_source.id)
    with patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)), \
         patch("connectors.git.get_embeddings_batch", AsyncMock(side_effect=Exception())), \
         patch("connectors.git.get_embedding", AsyncMock(side_effect=ValueError("truncated response"))), \
         patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)):
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert "Embedding-Fehler für 'PROG.CBL' (Chunk übersprungen): ValueError: truncated response" in test_source.sync_log

    # Every chunk failed both attempts -- the file must not silently claim
    # success while carrying zero actual content.
    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id,
        DocumentChunk.file_path == "PROG.CBL",
    ).all()
    assert len(chunks) == 0


@pytest.mark.anyio
async def test_git_connector_draining_fetch_documents_alone_does_not_move_progress(db_session, test_source):
    """
    Regression (O-075): parsed_files/progress used to be updated inside
    fetch_documents() -- i.e. the moment a file was read off disk and queued
    for embedding, not when it actually finished embedding and got saved.
    Reading files from a local git worktree is fast; once fetch_documents()
    drained, nothing updated these fields again for the rest of the (often
    much longer) embedding tail. Live observed against a real CardDemo
    import: the progress display froze at 89% for over an hour while
    genuine embedding work continued in the background.

    Draining fetch_documents() completely without ever completing an embed
    must leave parsed_files/progress untouched -- they may only advance from
    actual completions in sync()'s own processing loop (see the next test).
    """
    connector = GitConnector(test_source.id)
    # Bound to the connector's own db session, matching how sync() itself
    # loads self.source -- assigning the fixture's db_session-bound object
    # directly here would make self.db.commit() inside fetch_documents() a
    # no-op for it (different session, never part of that unit of work).
    connector.source = connector.db.query(KnowledgeSource).filter(KnowledgeSource.id == test_source.id).first()

    docs = [doc async for doc in connector.fetch_documents()]
    assert len(docs) == 2  # PROG.CBL + README.md, from the git_remote fixture

    db_session.refresh(test_source)
    assert test_source.total_files == 2  # legitimately set during fetch_documents()
    assert test_source.parsed_files == 0
    assert test_source.progress == 0


@pytest.mark.anyio
async def test_git_connector_progress_advances_only_as_files_actually_complete(db_session, test_source):
    """Complement to the test above: a full sync() must leave parsed_files
    matching the true number of completed documents, driven by the
    completion loop rather than the (now progress-silent) fetch_documents()."""
    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert test_source.parsed_files == test_source.total_files == 2
    assert test_source.progress == 100


@pytest.mark.anyio
async def test_git_connector_skips_known_binary_formats_instead_of_embedding_garbage(db_session, test_source, git_remote):
    """
    Regression (O-074): GitConnector had no file-type filtering at all,
    unlike folder.py/webdav.py's SUPPORTED_EXTENSIONS allowlist -- every
    file in the repo was read with open(path, "r", errors="ignore") and fed
    to the text embedding model, images included. Live verified against a
    real CardDemo import: a PNG's raw bytes "decode" into control-character
    garbage that still gets chunked and embedded, wasting Ollama capacity
    and polluting the vector index with noise that can surface as a false
    positive search result later. There is no image-understanding component
    anywhere in the pipeline (only PDFs get an OCR fallback, see O-031) --
    embedding a PNG can never produce anything meaningful.
    """
    _commit_file(git_remote, "diagrams/architecture.png", "not real PNG bytes, extension is what matters here", "add diagram")

    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert "[SKIP] 'diagrams/architecture.png' ist ein Binärformat" in test_source.sync_log

    # The .png must never reach the embedding pipeline -- no chunk, no
    # SourceScanFile row (so a future sync can't mistake it for "already
    # handled" either).
    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id,
        DocumentChunk.file_path == "diagrams/architecture.png",
    ).all()
    assert len(chunks) == 0
    scan_file = db_session.query(SourceScanFile).filter(
        SourceScanFile.source_id == test_source.id,
        SourceScanFile.file_path == "diagrams/architecture.png",
    ).first()
    assert scan_file is None

    # The legitimate COBOL/Markdown files must still be processed normally --
    # this must not turn into a blanket skip.
    cobol_chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id,
        DocumentChunk.file_path == "PROG.CBL",
    ).all()
    assert len(cobol_chunks) >= 1


@pytest.mark.anyio
async def test_git_connector_skips_non_utf8_content_despite_text_looking_extension(db_session, test_source, git_remote):
    """
    Regression (O-074, Ergänzung): eine reine Endungssperre erfasst eine
    EBCDIC-Mainframe-Datei wie AWS.M2.CARDDEMO.ACCTDATA.PS nicht -- ".PS"
    sieht wie eine normale Textdatei aus. Live beobachtet: der Byteinhalt
    ist kein UTF-8 und "dekodiert" mit errors="ignore" zu genau demselben
    Steuerzeichen-Datenmüll wie ein Bild. Eine EBCDIC-kodierte Ziffernfolge
    fällt bereits beim strikten UTF-8-Decode durch (0xF0-0xF9 ohne gültige
    Fortsetzungsbytes ergibt hier UnicodeDecodeError).
    """
    ebcdic_digits = bytes([0xF0, 0xF1, 0xF2, 0xF3, 0xF4] * 20)
    _commit_file(git_remote, "AWS.M2.CARDDEMO.ACCTDATA.PS", "placeholder", "add mainframe data file")
    _commit_binary_file(git_remote, "AWS.M2.CARDDEMO.ACCTDATA.PS", ebcdic_digits, "overwrite with EBCDIC bytes")

    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert "[SKIP] 'AWS.M2.CARDDEMO.ACCTDATA.PS' ist kein UTF-8-Text" in test_source.sync_log

    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id,
        DocumentChunk.file_path == "AWS.M2.CARDDEMO.ACCTDATA.PS",
    ).all()
    assert len(chunks) == 0
    scan_file = db_session.query(SourceScanFile).filter(
        SourceScanFile.source_id == test_source.id,
        SourceScanFile.file_path == "AWS.M2.CARDDEMO.ACCTDATA.PS",
    ).first()
    assert scan_file is None


@pytest.mark.anyio
async def test_git_connector_skips_valid_utf8_dominated_by_control_characters(db_session, test_source, git_remote):
    """Auch valides UTF-8 kann Datenmüll sein -- z. B. ein binäres Format,
    dessen Bytes zufällig als gültiges UTF-8 durchgehen, aber fast nur aus
    Steuerzeichen besteht. Die Endungssperre allein greift hier nicht (neue
    Endung), die Steuerzeichen-Quote schon."""
    mostly_control = ("\x01\x02\x03\x04\x05" * 100).encode("utf-8")
    _commit_binary_file(git_remote, "weird.dat", mostly_control, "add control-char-heavy file")

    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert "[SKIP] 'weird.dat' ist kein UTF-8-Text" in test_source.sync_log
    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == test_source.id,
        DocumentChunk.file_path == "weird.dat",
    ).all()
    assert len(chunks) == 0


@pytest.mark.anyio
async def test_git_connector_logs_embedding_start_per_file(db_session, test_source):
    """
    O-072: bis zu EMBED_CONCURRENCY Dateien werden gleichzeitig eingebettet,
    aber bisher loggten git.py/base.py nur "fertig"/"Fehler" pro Datei --
    aus dem Sync-Log allein liess sich nie ablesen, an welcher der noch
    offenen Dateien gerade tatsaechlich gearbeitet wird.
    """
    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert "Embedding gestartet für 'PROG.CBL'." in test_source.sync_log
    assert "Embedding gestartet für 'README.md'." in test_source.sync_log
