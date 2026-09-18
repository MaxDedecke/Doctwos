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


def _delete_file(repo: str, rel_path: str, message: str) -> None:
    subprocess.run(["git", "-C", repo, "rm", rel_path], check=True, capture_output=True)
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
    _commit_file(path, "module-a/src/main/java/duplicate/App.java", "package duplicate; public class App {}\n", "module a app")
    _commit_file(path, "module-b/src/main/java/duplicate/App.java", "package duplicate; public class App {}\n", "module b app")
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
    _commit_file(path, "run.sh", "#!/bin/sh\njava -cp app.jar app.Main\n", "launcher")
    _commit_file(
        path,
        "app/src/main/java/app/Main.java",
        """package app;
public class Main {
  public static void main(String[] args) {
    Main.class.getResource("/templates/report.xsl");
    Main.class.getResource("/views/result.jsp");
    Main.class.getResource(path);
  }
}
""",
        "cross-language entrypoint",
    )
    _commit_file(
        path,
        "app/src/main/resources/templates/report.xsl",
        """<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
  <xsl:template match="/">
    <xsl:value-of select="document('input.xml')/root/value"/>
  </xsl:template>
</xsl:stylesheet>
""",
        "cross-language stylesheet",
    )
    _commit_file(
        path,
        "app/src/main/resources/templates/input.xml",
        "<root><value>ok</value></root>\n",
        "cross-language input",
    )
    _commit_file(
        path,
        "app/src/main/resources/views/result.jsp",
        '<jsp:include page="fragment.jsp" />\n',
        "cross-language view",
    )
    _commit_file(
        path,
        "app/src/main/resources/views/fragment.jsp",
        "<p>fragment</p>\n",
        "cross-language fragment",
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

    db_session.expire_all()
    source_state = db_session.query(KnowledgeSource).filter(KnowledgeSource.id == java_source.id).one()
    assert source_state.sync_status == "completed", source_state.last_error
    entities = db_session.query(CodeEntity).filter(CodeEntity.source_id == java_source.id).all()
    by_qname = {entity.qualified_name: entity for entity in entities}
    assert "api.Service" in by_qname
    assert "app.Client#call()" in by_qname

    edges = db_session.query(CodeEdge).filter(CodeEdge.source_id == java_source.id).all()
    call = next(
        edge
        for edge in edges
        if edge.type == "CALLS"
        and (edge.meta_json or {}).get("target_qualified_name") == "api.Service#run(int)"
    )
    assert call.resolution == "resolved"
    assert call.dst_entity_id == by_qname["api.Service#run(int)"].id

    ambiguous = next(
        edge for edge in edges if edge.type == "USES_TYPE" and edge.dst_name == "Shared"
    )
    assert ambiguous.resolution == "unresolved"
    assert ambiguous.dst_entity_id is None
    assert ambiguous.meta_json["resolution_reason"] == "ambiguous_type"

    roots = {
        entity.file_path: entity
        for entity in entities
        if (entity.meta_json or {}).get("is_file_root")
    }
    main = (
        db_session.query(CodeEntity)
        .filter(
            CodeEntity.source_id == java_source.id,
            CodeEntity.file_path == "app/src/main/java/app/Main.java",
            CodeEntity.type == "method",
            CodeEntity.qualified_name.like("%#main(%)"),
        )
        .one()
    )
    cross_edges = [
        edge
        for edge in edges
        if edge.type in {"STARTS_JAVA", "USES_RESOURCE", "READS_XML", "INCLUDES"}
    ]
    assert {edge.type for edge in cross_edges} == {
        "STARTS_JAVA", "USES_RESOURCE", "READS_XML", "INCLUDES"
    }
    assert next(edge for edge in cross_edges if edge.type == "STARTS_JAVA").dst_entity_id == main.id
    assert next(
        edge for edge in cross_edges
        if edge.type == "USES_RESOURCE" and edge.dst_entity_id == roots["app/src/main/resources/templates/report.xsl"].id
    ).resolution == "resolved"
    assert next(
        edge for edge in cross_edges
        if edge.type == "READS_XML" and edge.dst_entity_id == roots["app/src/main/resources/templates/input.xml"].id
    ).resolution == "resolved"
    assert next(
        edge for edge in cross_edges
        if edge.type == "INCLUDES" and edge.dst_entity_id == roots["app/src/main/resources/views/fragment.jsp"].id
    ).resolution == "resolved"
    assert all(
        edge.meta_json["evidence"]["source"]["file_path"]
        == db_session.get(CodeEntity, edge.src_entity_id).file_path
        for edge in cross_edges
    )
    dynamic = next(edge for edge in cross_edges if edge.type == "USES_RESOURCE" and edge.resolution == "dynamic")
    assert dynamic.dst_entity_id is None
    assert dynamic.meta_json["resolution_reason"] == "dynamic_resource_expression"


@pytest.mark.anyio
async def test_java_same_qualified_class_in_separate_modules_is_not_merged(db_session, java_source):
    connector = GitConnector(java_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    apps = (
        db_session.query(CodeEntity)
        .filter(CodeEntity.source_id == java_source.id, CodeEntity.qualified_name == "duplicate.App")
        .order_by(CodeEntity.file_path)
        .all()
    )
    assert [app.file_path for app in apps] == [
        "module-a/src/main/java/duplicate/App.java",
        "module-b/src/main/java/duplicate/App.java",
    ]
    assert {app.meta_json["module"] for app in apps} == {"module-a", "module-b"}


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
    call_before = next(
        edge
        for edge in db_session.query(CodeEdge)
        .filter(CodeEdge.source_id == java_source.id, CodeEdge.type == "CALLS")
        .all()
        if (edge.meta_json or {}).get("target_qualified_name") == "api.Service#run(int)"
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
    call_after = next(
        edge
        for edge in db_session.query(CodeEdge)
        .filter(CodeEdge.source_id == java_source.id, CodeEdge.type == "CALLS")
        .all()
        if (edge.meta_json or {}).get("target_qualified_name") == "api.Service#run(int)"
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


@pytest.mark.anyio
async def test_resource_target_change_reparses_unchanged_include_source(
    db_session, java_source, java_remote
):
    """O-252: a changed included resource invalidates its unchanged source."""
    connector = GitConnector(java_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    result_before = (
        db_session.query(SourceScanFile)
        .filter(
            SourceScanFile.source_id == java_source.id,
            SourceScanFile.file_path == "app/src/main/resources/views/result.jsp",
        )
        .one()
    )
    result_fingerprint_before = result_before.analysis_fingerprint

    _commit_file(
        java_remote,
        "app/src/main/resources/views/fragment.jsp",
        "<p>changed fragment</p>\n",
        "change included resource",
    )
    connector = GitConnector(java_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    db_session.expire_all()
    result_after = (
        db_session.query(SourceScanFile)
        .filter(
            SourceScanFile.source_id == java_source.id,
            SourceScanFile.file_path == "app/src/main/resources/views/result.jsp",
        )
        .one()
    )
    assert result_after.analysis_fingerprint != result_fingerprint_before


@pytest.mark.anyio
async def test_deleted_target_reparses_unchanged_java_caller_as_unresolved(
    db_session, java_source, java_remote
):
    """O-252: deleting a target must not silently remove its caller edge."""
    connector = GitConnector(java_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    _delete_file(java_remote, "api/Service.java", "remove service")
    connector = GitConnector(java_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    caller = (
        db_session.query(CodeEntity)
        .filter(
            CodeEntity.source_id == java_source.id,
            CodeEntity.file_path == "app/Client.java",
            CodeEntity.type == "class",
        )
        .one()
    )
    caller_edges = (
        db_session.query(CodeEdge)
        .filter(CodeEdge.source_id == java_source.id, CodeEdge.src_entity_id == caller.id)
        .all()
    )
    call = next(edge for edge in caller_edges if edge.type == "CALLS")
    assert call.dst_entity_id is None
    assert call.resolution == "unresolved"
