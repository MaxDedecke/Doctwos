"""T5.1: Ende-zu-Ende-Lebenszyklus für gemischte Git-Repositories.

Der Test lässt Git, den Connector, Java-/COBOL-Parser, Persistenz und Resume
gemeinsam laufen. Nur der externe Embedding-Dienst wird kontrolliert gemockt.
"""

from __future__ import annotations

import os
import subprocess
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

from connectors.git import GitConnector
from db import SessionLocal
from models.database import CodeEdge, CodeEntity, DocumentChunk, KnowledgeSource, SourceScanFile


def _init_remote(path: str) -> None:
    subprocess.run(["git", "init", "--initial-branch=main", path], check=True, capture_output=True)
    subprocess.run(["git", "-C", path, "config", "user.email", "test@doctus.local"], check=True)
    subprocess.run(["git", "-C", path, "config", "user.name", "Doctus Test"], check=True)


def _commit_file(repo: str, rel_path: str, content: str, message: str) -> None:
    full_path = os.path.join(repo, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    subprocess.run(["git", "-C", repo, "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", message], check=True, capture_output=True)


def _delete_file(repo: str, rel_path: str, message: str) -> None:
    subprocess.run(["git", "-C", repo, "rm", rel_path], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", message], check=True, capture_output=True)


@pytest.fixture
def t51_remote(tmp_path):
    path = str(tmp_path / "t51-remote.git")
    _init_remote(path)
    _commit_file(
        path,
        "src/main/java/com/acme/PaymentService.java",
        """package com.acme;
public class PaymentService {
    public void charge() {}
}
""",
        "add payment service",
    )
    _commit_file(
        path,
        "src/main/java/com/acme/PaymentClient.java",
        """package com.acme;
class PaymentClient {
    void pay() { new PaymentService().charge(); }
}
""",
        "add payment client",
    )
    _commit_file(
        path,
        "src/main/java/com/acme/Legacy.java",
        "package com.acme; class Legacy { void old() {} }\n",
        "add legacy class",
    )
    _commit_file(
        path,
        "src/main/cobol/PAYMENT.CBL",
        """       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYMENT.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY "PAYMENT".
           STOP RUN.
""",
        "add cobol program",
    )
    return path


@pytest.fixture
def t51_source(t51_remote, tmp_path, monkeypatch, db_session):
    monkeypatch.setattr("connectors.git.REPOS_ROOT", str(tmp_path / "repos"))
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": f"t51-team-{tmp_path.name}"},
    ).scalar_one()
    project_id = db_session.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) "
            "VALUES (:name, :team_id, now()) RETURNING id"
        ),
        {"name": f"t51-project-{tmp_path.name}", "team_id": team_id},
    ).scalar_one()
    source = KnowledgeSource(
        name=f"T5.1 Git {tmp_path.name}",
        type="Git",
        url=t51_remote,
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
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete(
        synchronize_session=False
    )
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


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


async def _sync(source_id: int) -> None:
    connector = GitConnector(source_id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()


@pytest.mark.anyio
async def test_t51_mixed_repository_delete_abort_and_resume_end_to_end(
    db_session, t51_source, t51_remote
):
    """T5.1: gemischter Repo-Lebenszyklus inklusive abgebrochenem Resume."""
    await _sync(t51_source.id)

    db_session.refresh(t51_source)
    initial_cursor = t51_source.sync_cursor["last_commit"]
    assert t51_source.sync_status == "completed"
    assert t51_source.total_files == t51_source.parsed_files == 4

    initial_entities = {
        entity.qualified_name
        for entity in db_session.query(CodeEntity)
        .filter(CodeEntity.source_id == t51_source.id)
        .all()
    }
    assert "com.acme.PaymentService" in initial_entities
    assert "com.acme.PaymentClient" in initial_entities
    assert "PAYMENT" in initial_entities
    assert "com.acme.Legacy" in initial_entities

    initial_edges = db_session.query(CodeEdge).filter(CodeEdge.source_id == t51_source.id).all()
    assert any(edge.type == "CALLS" and edge.resolution == "resolved" for edge in initial_edges)

    _commit_file(
        t51_remote,
        "src/main/java/com/acme/PaymentClient.java",
        """package com.acme;
class PaymentClient {
    void pay() { new PaymentService().charge(); }
    void refund() { new PaymentService().charge(); }
}
""",
        "change payment client",
    )
    _commit_file(
        t51_remote,
        "src/main/java/com/acme/PaymentReport.java",
        'package com.acme; class PaymentReport { String title() { return "payments"; } }\n',
        "add payment report",
    )
    _commit_file(
        t51_remote,
        "src/main/cobol/PAYMENT.CBL",
        """       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYMENT.
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY "PAYMENT UPDATED".
           STOP RUN.
""",
        "change cobol program",
    )
    _delete_file(t51_remote, "src/main/java/com/acme/Legacy.java", "remove legacy class")

    connector = GitConnector(t51_source.id)
    original_save = connector._save_document_chunks
    abort_once = True

    async def abort_on_client(doc, chunks, parse_result=None):
        nonlocal abort_once
        if abort_once and doc["storage_key"] == "src/main/java/com/acme/PaymentClient.java":
            abort_once = False
            raise RuntimeError("synthetic T5.1 interruption")
        return await original_save(doc, chunks, parse_result)

    patches = _embedding_patches()
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch.object(connector, "_save_document_chunks", side_effect=abort_on_client),
    ):
        await connector.sync()

    db_session.expire_all()
    db_session.refresh(t51_source)
    assert t51_source.sync_status == "error"
    assert "synthetic T5.1 interruption" in t51_source.last_error
    assert t51_source.sync_cursor["last_commit"] == initial_cursor

    resume_connector = GitConnector(t51_source.id)
    patches = _embedding_patches()
    with patches[0], patches[1] as embed_batch, patches[2], patches[3]:
        await resume_connector.sync()

    db_session.expire_all()
    db_session.refresh(t51_source)
    assert t51_source.sync_status == "completed"
    assert t51_source.sync_cursor["last_commit"] != initial_cursor
    # Die Fortschrittszähler beziehen sich auf die in diesem Resume-Lauf
    # tatsächlich erneut verarbeiteten Dokumente, nicht auf alle Dateien des
    # Repositories. Die vollständige Endlage wird unten über Scan-Pfade und
    # Entities geprüft.
    assert t51_source.parsed_files == t51_source.total_files
    scan_paths = {
        scan.file_path
        for scan in db_session.query(SourceScanFile)
        .filter(SourceScanFile.source_id == t51_source.id)
        .all()
    }
    assert scan_paths == {
        "src/main/java/com/acme/PaymentService.java",
        "src/main/java/com/acme/PaymentClient.java",
        "src/main/java/com/acme/PaymentReport.java",
        "src/main/cobol/PAYMENT.CBL",
    }

    final_entities = {
        entity.qualified_name
        for entity in db_session.query(CodeEntity)
        .filter(CodeEntity.source_id == t51_source.id)
        .all()
    }
    assert "com.acme.Legacy" not in final_entities
    assert "com.acme.PaymentReport" in final_entities
    assert "PAYMENT" in final_entities

    final_edges = db_session.query(CodeEdge).filter(CodeEdge.source_id == t51_source.id).all()
    assert any(edge.type == "CALLS" and edge.resolution == "resolved" for edge in final_edges)

    resumed_text = [text for call in embed_batch.await_args_list for text in call.args[0]]
    assert not any("public class PaymentService" in text for text in resumed_text)
