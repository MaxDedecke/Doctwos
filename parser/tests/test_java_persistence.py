"""T3.4: Java entities/edges through the Git persistence lifecycle."""

from __future__ import annotations

import os
import subprocess
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from db import SessionLocal
from models.database import CodeEdge, CodeEntity, DocumentChunk, KnowledgeSource, SourceScanFile
from connectors.git import GitConnector


def _init_remote(path: str) -> None:
    subprocess.run(["git", "init", "--initial-branch=main", path], check=True, capture_output=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "test@doctus.local"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "Doctus Test"], check=True)


def _commit_file(repo: str, rel_path: str, content: str, message: str) -> None:
    full = os.path.join(repo, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(content)
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", message], check=True, capture_output=True)


@pytest.fixture
def java_remote(tmp_path):
    path = str(tmp_path / "java-remote.git")
    _init_remote(path)
    _commit_file(
        path,
        "api/Service.java",
        "package api; public class Service { public Service() {} public void run(int value) {} }\n",
        "service",
    )
    _commit_file(
        path,
        "app/Client.java",
        """package app;
import api.Service;
class Client { void call() { new Service().run(1); } }
""",
        "client",
    )
    _commit_file(path, "one/Shared.java", "package one; public class Shared {}\n", "one")
    _commit_file(path, "two/Shared.java", "package two; public class Shared {}\n", "two")
    _commit_file(
        path,
        "app/Ambiguous.java",
        """package app;
import one.*;
import two.*;
class Ambiguous { Shared value; }
""",
        "ambiguous",
    )
    return path


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def java_source(java_remote, tmp_path, monkeypatch, db_session):
    monkeypatch.setattr("connectors.git.REPOS_ROOT", str(tmp_path / "repos"))
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": f"java-team-{tmp_path.name}"},
    ).scalar_one()
    project_id = db_session.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"
        ),
        {"name": f"java-project-{tmp_path.name}", "team_id": team_id},
    ).scalar_one()
    source = KnowledgeSource(
        name=f"Java Git {tmp_path.name}",
        type="Git",
        url=java_remote,
        branch="main",
        project_id=project_id,
        team_id=team_id,
        spaces={"language_extensions": {"java": [".java"]}},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    yield source

    db_session.query(CodeEdge).filter(CodeEdge.source_id == source.id).delete(
        synchronize_session=False
    )
    db_session.query(CodeEntity).filter(CodeEntity.source_id == source.id).delete(
        synchronize_session=False
    )
    db_session.query(SourceScanFile).filter(SourceScanFile.source_id == source.id).delete(
        synchronize_session=False
    )
    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete(
        synchronize_session=False
    )
    db_session.delete(source)
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


def _embedding_patches():
    return (
        patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)),
        patch(
            "connectors.git.get_embeddings_batch",
            AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts]),
        ),
        patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)),
        patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)),
    )


@pytest.mark.anyio
async def test_java_git_persistence_resolves_multiple_files_and_keeps_ambiguity(
    db_session, java_source
):
    connector = GitConnector(java_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    entities = db_session.query(CodeEntity).filter(CodeEntity.source_id == java_source.id).all()
    by_qname = {entity.qualified_name: entity for entity in entities}
    assert "api.Service" in by_qname
    assert "app.Client#call()" in by_qname

    edges = db_session.query(CodeEdge).filter(CodeEdge.source_id == java_source.id).all()
    call = next(edge for edge in edges if edge.type == "CALLS")
    assert call.resolution == "resolved"
    assert call.dst_entity_id == by_qname["api.Service#run(int)"].id

    ambiguous = next(
        edge
        for edge in edges
        if edge.type == "USES_TYPE" and edge.dst_name == "Shared"
    )
    assert ambiguous.resolution == "unresolved"
    assert ambiguous.dst_entity_id is None
    assert ambiguous.meta_json["resolution_reason"] == "ambiguous_type"


@pytest.mark.anyio
async def test_java_reparse_preserves_incoming_edge_and_resume_skips_unchanged_files(
    db_session, java_source, java_remote
):
    connector = GitConnector(java_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    service_before = (
        db_session.query(CodeEntity)
        .filter(
            CodeEntity.source_id == java_source.id,
            CodeEntity.qualified_name == "api.Service",
        )
        .one()
    )
    call_before = (
        db_session.query(CodeEdge)
        .filter(CodeEdge.source_id == java_source.id, CodeEdge.type == "CALLS")
        .one()
    )

    _commit_file(
        java_remote,
        "api/Service.java",
        "package api; public class Service { public Service() {} public void run(int value) {} public void added() {} }\n",
        "service change",
    )
    connector = GitConnector(java_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    db_session.expire_all()
    service_after = (
        db_session.query(CodeEntity)
        .filter(
            CodeEntity.source_id == java_source.id,
            CodeEntity.qualified_name == "api.Service",
        )
        .one()
    )
    call_after = (
        db_session.query(CodeEdge)
        .filter(CodeEdge.source_id == java_source.id, CodeEdge.type == "CALLS")
        .one()
    )
    assert service_after.id == service_before.id
    assert call_after.id == call_before.id
    assert call_after.resolution == "resolved"
    run_after = (
        db_session.query(CodeEntity)
        .filter(
            CodeEntity.source_id == java_source.id,
            CodeEntity.qualified_name == "api.Service#run(int)",
        )
        .one()
    )
    assert call_after.dst_entity_id == run_after.id

    # The following unchanged run exercises the SourceScanFile analysis
    # fingerprint resume path.  No document reaches the embedding function.
    connector = GitConnector(java_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1] as embed_batch, patches[2], patches[3]:
        await connector.sync()
    assert embed_batch.await_count == 0
