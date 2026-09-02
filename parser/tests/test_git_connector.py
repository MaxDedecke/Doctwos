import os
import subprocess

import pytest
from sqlalchemy import text
from unittest.mock import patch, AsyncMock

from db import SessionLocal
from models.database import KnowledgeSource, SourceScanFile, DocumentChunk
from connectors.git import GitConnector
import git_utils


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
    )


@pytest.mark.anyio
async def test_git_connector_initial_sync(db_session, test_source):
    connector = GitConnector(test_source.id)
    p1, p2, p3 = _patched_sync(connector)
    with p1, p2, p3:
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
    p1, p2, p3 = _patched_sync(connector1)
    with p1, p2, p3:
        await connector1.sync()

    # Remote aendert sich: PROG.CBL modifiziert, README.md geloescht, NEW.CBL neu
    _commit_file(git_remote, "PROG.CBL", "IDENTIFICATION DIVISION.\nPROGRAM-ID. PROG.\nMORE.\n", "update")
    _delete_file(git_remote, "README.md", "remove readme")
    _commit_file(git_remote, "NEW.CBL", "IDENTIFICATION DIVISION.\nPROGRAM-ID. NEW.\n", "add new")

    connector2 = GitConnector(test_source.id)
    p1, p2, p3 = _patched_sync(connector2)
    with p1, p2, p3:
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
    first_batch, first_single, first_model = _patched_sync(connector)
    with first_batch, first_single, first_model:
        await connector.sync()

    embed_batch = AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts])
    connector = GitConnector(test_source.id)
    with patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)), \
         patch("connectors.git.get_embeddings_batch", embed_batch), \
         patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)):
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
         patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)):
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
                 patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)):
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
