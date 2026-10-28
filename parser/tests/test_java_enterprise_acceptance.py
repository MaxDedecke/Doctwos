"""Git → parser → persistence → graph context, with only embeddings mocked."""

import importlib
import shutil
import subprocess
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from connectors.git import GitConnector
from db import SessionLocal
from doctus_models.database import (
    Team,
    Project,
    KnowledgeSource,
    CodeEntity,
    CodeEdge,
    DocumentChunk,
    SourceScanFile,
)

FIXTURE = Path(__file__).parent / "fixtures" / "java25_enterprise"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


@pytest.fixture
def enterprise(tmp_path, monkeypatch):
    remote = tmp_path / "remote"
    shutil.copytree(FIXTURE, remote)
    git(remote, "init", "--initial-branch=main")
    git(remote, "config", "user.email", "parser-test@example.invalid")
    git(remote, "config", "user.name", "Parser Test")
    git(remote, "add", ".")
    git(remote, "commit", "-m", "enterprise fixture")
    monkeypatch.setattr("connectors.git.REPOS_ROOT", str(tmp_path / "repos"))
    monkeypatch.setenv("PARSE_WORKERS", "0")
    monkeypatch.setenv("DOCTUS_ASCIIDOC_ATTRIBUTES", '{"lang-de":""}')
    db = SessionLocal()
    team = Team(name="enterprise-" + uuid.uuid4().hex)
    db.add(team)
    db.flush()
    project = Project(name="enterprise", team_id=team.id)
    db.add(project)
    db.flush()
    source = KnowledgeSource(
        name="enterprise",
        type="Git",
        url=str(remote),
        branch="main",
        team_id=team.id,
        project_id=project.id,
    )
    db.add(source)
    db.commit()
    try:
        yield db, source.id, remote
    finally:
        db.delete(project)
        db.commit()
        db.delete(team)
        db.commit()
        db.close()


async def sync_source(db, source_id):
    connector = GitConnector(source_id)
    try:
        with (
            patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)),
            patch(
                "connectors.git.get_embeddings_batch",
                AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts]),
            ),
            patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)),
            patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)),
        ):
            await connector.sync()
    finally:
        connector.db.close()
    db.expire_all()
    source = db.get(KnowledgeSource, source_id)
    assert source.sync_status == "completed", source.last_error


def assert_static_graph(db, source_id):
    entities = db.query(CodeEntity).filter(CodeEntity.source_id == source_id).all()
    by_id = {e.id: e for e in entities}
    edges = db.query(CodeEdge).filter(CodeEdge.source_id == source_id).all()
    dispatch = [e for e in edges if e.type == "DISPATCHES_TO"]
    assert any(
        by_id[e.dst_entity_id].qualified_name == "demo.impl.Fast#submit(Order)" for e in dispatch
    )
    assert not any(
        by_id[e.dst_entity_id].qualified_name == "demo.impl.Slow#submit(Order)" for e in dispatch
    )
    for key in ["orders.timeout", "orders.label"]:
        assert any(
            e.type == "REFERENCES_PROPERTY_KEY" and e.dst_name == key and e.resolution == "resolved"
            for e in edges
        )
    assert any(
        e.type == "endpoint"
        and e.meta_json.get("path") == "/orders"
        and e.meta_json.get("http_method") == "POST"
        for e in entities
    )
    assert any(e.qualified_name == "Hello#main()" for e in entities)
    assert not any(
        e.type == "MAPS_XML_ELEMENT" and "localOnly" in by_id[e.src_entity_id].qualified_name
        for e in edges
    )
    soap = next(
        e for e in entities if e.type == "endpoint" and e.meta_json.get("framework") == "jaxws"
    )
    seen, queue = set(), [soap.id]
    while queue:
        identity = queue.pop(0)
        if identity in seen:
            continue
        seen.add(identity)
        queue.extend(
            e.dst_entity_id
            for e in edges
            if e.src_entity_id == identity
            and e.resolution == "resolved"
            and e.dst_entity_id is not None
        )
    assert any(by_id[i].type == "xsd_complex_type" and by_id[i].name == "OrderType" for i in seen)
    for row in db.query(SourceScanFile).filter(SourceScanFile.source_id == source_id).all():
        expected = "text_fallback" if row.language == "text" else "complete"
        assert row.parse_status == expected, (row.file_path, row.parse_status, row.parse_error)


def assert_retrieval(db, source_id, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "backend"))
    retrieval = importlib.import_module("services.graph_retrieval")
    method = (
        db.query(CodeEntity)
        .filter(
            CodeEntity.source_id == source_id,
            CodeEntity.qualified_name == "demo.web.OrderController#create(Order)",
        )
        .one()
    )
    chunk = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == source_id,
            DocumentChunk.file_path == method.file_path,
            DocumentChunk.start_line <= method.start_line,
            DocumentChunk.end_line >= method.end_line,
        )
        .first()
    )
    context = retrieval.expand_chunks_with_graph(db, [chunk], token_budget=8192)
    assert any(c.file_path.endswith("/Fast.java") and '"fast"' in c.content for c in context)
    book = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.source_id == source_id, DocumentChunk.file_path == "docs/index.adoc")
        .first()
    )
    context = retrieval.expand_chunks_with_graph(db, [book], token_budget=8192)
    excerpt = next(c for c in context if c.file_path.endswith("/OrderController.java"))
    assert "@PostMapping" in excerpt.content and "public String create" in excerpt.content
    assert "tag::endpoint" not in excerpt.content and excerpt.start_line == 13


@pytest.mark.anyio
async def test_enterprise_project_import_resume_context_and_attribute_change(
    enterprise, monkeypatch
):
    db, source_id, remote = enterprise
    await sync_source(db, source_id)
    assert_static_graph(db, source_id)
    assert_retrieval(db, source_id, monkeypatch)
    chunks = {
        row.id for row in db.query(DocumentChunk).filter(DocumentChunk.source_id == source_id).all()
    }
    await sync_source(db, source_id)
    assert chunks == {
        row.id for row in db.query(DocumentChunk).filter(DocumentChunk.source_id == source_id).all()
    }
    (remote / "docs" / "attributes.adoc").write_text(
        ":product: Nächste Version\n:chapters: chapters\n", encoding="utf-8"
    )
    git(remote, "add", ".")
    git(remote, "commit", "-m", "change documentation attribute")
    await sync_source(db, source_id)
    root = (
        db.query(CodeEntity)
        .filter(
            CodeEntity.source_id == source_id,
            CodeEntity.type == "asciidoc_document",
            CodeEntity.file_path == "docs/index.adoc",
        )
        .one()
    )
    assert any(
        item["title"] == "Nächste Version Schnittstellen"
        for item in root.meta_json["composition_outline"]
    )
    assert_static_graph(db, source_id)
    pom = remote / "web" / "pom.xml"
    content = pom.read_text(encoding="utf-8")
    content = content.replace(
        "<dependency><groupId>demo</groupId><artifactId>impl</artifactId><version>1</version><scope>runtime</scope></dependency>",
        "",
    )
    pom.write_text(content, encoding="utf-8")
    git(remote, "add", ".")
    git(remote, "commit", "-m", "remove runtime implementation")
    await sync_source(db, source_id)
    injected = (
        db.query(CodeEdge)
        .join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id)
        .filter(
            CodeEdge.source_id == source_id,
            CodeEdge.type == "INJECTS",
            CodeEntity.qualified_name == "demo.web.OrderController#port",
        )
        .one()
    )
    assert injected.resolution == "unresolved" and injected.dst_entity_id is None
    assert (
        not db.query(CodeEdge)
        .filter(CodeEdge.source_id == source_id, CodeEdge.type == "DISPATCHES_TO")
        .count()
    )
