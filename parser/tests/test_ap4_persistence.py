"""
AP-4: Entity-/Kanten-Persistenz (Pass 1, cobol_persist.py) + globale
Nachauflösung (Pass 2, tasks/edge_resolver.py) end-to-end über
GitConnector.sync() -- braucht einen erreichbaren DB-Host, siehe
test_git_connector.py fuer denselben Docker-Netz-Vorbehalt.
"""

import os
import subprocess

import pytest
from sqlalchemy import text
from unittest.mock import patch, AsyncMock

from db import SessionLocal
from models.database import CodeEdge, CodeEntity, KnowledgeSource, SourceScanFile, DocumentChunk
from connectors.git import GitConnector


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


_MAIN_CBL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAIN.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-FLAG              PIC X(1).
       PROCEDURE DIVISION.
       MAIN-PARA.
           DISPLAY SHARED-FIELD.
           COPY FIELDS.
           PERFORM SUB-PARA.
           CALL 'SUB'.
       SUB-PARA.
           MOVE 'Y' TO WS-FLAG.
"""

_SUB_CBL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SUB.
       PROCEDURE DIVISION.
       ONLY-PARA.
           STOP RUN.
"""

_FIELDS_CPY = """\
       01  SHARED-RECORD.
           05  SHARED-FIELD     PIC X(10).
"""


@pytest.fixture
def git_remote(tmp_path):
    path = str(tmp_path / "remote.git")
    _init_remote(path)
    _commit_file(path, "MAIN.CBL", _MAIN_CBL, "init main")
    _commit_file(path, "SUB.CBL", _SUB_CBL, "init sub")
    _commit_file(path, "FIELDS.CPY", _FIELDS_CPY, "init copybook")
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
    repos_root = str(tmp_path / "repos_root")
    monkeypatch.setattr("connectors.git.REPOS_ROOT", repos_root)

    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "ap4-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "ap4-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(
        name="AP4 Test Git", type="Git", url=git_remote, branch="main",
        project_id=project_id, team_id=team_id,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    yield source

    db_session.query(CodeEdge).filter(CodeEdge.source_id == source.id).delete(synchronize_session=False)
    db_session.query(CodeEntity).filter(CodeEntity.source_id == source.id).delete(synchronize_session=False)
    db_session.query(SourceScanFile).filter(SourceScanFile.source_id == source.id).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.delete(source)
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


def _patched_sync():
    return (
        patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)),
        patch("connectors.git.get_embeddings_batch", AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts])),
        patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)),
    )


async def _sync(source_id):
    connector = GitConnector(source_id)
    p1, p2, p3 = _patched_sync()
    with p1, p2, p3:
        await connector.sync()
    return connector


@pytest.mark.anyio
async def test_entities_and_edges_persisted_and_globally_resolved(db_session, test_source):
    await _sync(test_source.id)

    entities = db_session.query(CodeEntity).filter(CodeEntity.source_id == test_source.id).all()
    by_qname = {e.qualified_name: e for e in entities}

    assert "MAIN" in by_qname and by_qname["MAIN"].type == "program"
    assert "SUB" in by_qname and by_qname["SUB"].type == "program"
    assert "FIELDS" in by_qname and by_qname["FIELDS"].type == "copybook"
    assert "FIELDS.SHARED-RECORD.SHARED-FIELD" in by_qname
    assert by_qname["MAIN.MAIN-PARA"].parent_id == by_qname["MAIN"].id

    edges = db_session.query(CodeEdge).filter(CodeEdge.source_id == test_source.id).all()
    by_type = {}
    for e in edges:
        by_type.setdefault(e.type, []).append(e)

    # CALL/COPY sind global (scope_entity_id IS NULL) und erst durch Pass 2
    # aufgeloest -- beide muessen nach dem Sync resolved sein.
    call_edge = by_type["CALL"][0]
    assert call_edge.resolution == "resolved"
    assert call_edge.dst_entity_id == by_qname["SUB"].id
    assert call_edge.scope_entity_id is None

    copy_edge = by_type["COPY"][0]
    assert copy_edge.resolution == "resolved"
    assert copy_edge.dst_entity_id == by_qname["FIELDS"].id

    inherited_use = next(e for e in by_type["USES"] if e.dst_name == "SHARED-FIELD")
    assert inherited_use.resolution == "resolved"
    assert inherited_use.dst_entity_id == by_qname["FIELDS.SHARED-RECORD.SHARED-FIELD"].id
    assert inherited_use.scope_entity_id == by_qname["MAIN"].id

    # PERFORM ist lokal (E-1) und schon in Pass 1 aufgeloest.
    perform_edge = by_type["PERFORM"][0]
    assert perform_edge.resolution == "resolved"
    assert perform_edge.dst_entity_id == by_qname["MAIN.SUB-PARA"].id
    assert perform_edge.scope_entity_id == by_qname["MAIN"].id


@pytest.mark.anyio
async def test_reparse_preserves_entity_id_and_keeps_external_edges(db_session, test_source, git_remote):
    await _sync(test_source.id)

    sub_before = db_session.query(CodeEntity).filter(
        CodeEntity.source_id == test_source.id, CodeEntity.qualified_name == "SUB",
    ).one()
    call_edge_before = db_session.query(CodeEdge).filter(
        CodeEdge.source_id == test_source.id, CodeEdge.type == "CALL",
    ).one()
    assert call_edge_before.dst_entity_id == sub_before.id

    # SUB.CBL aendert sich (neuer Paragraph), MAIN.CBL/FIELDS.CPY bleiben
    # unveraendert und werden dank NF-004-Resume-Skip in diesem Sync gar
    # nicht neu geparst.
    _commit_file(
        git_remote, "SUB.CBL",
        _SUB_CBL + "       EXTRA-PARA.\n           CONTINUE.\n",
        "add paragraph to sub",
    )
    await _sync(test_source.id)

    db_session.expire_all()
    sub_after = db_session.query(CodeEntity).filter(
        CodeEntity.source_id == test_source.id, CodeEntity.qualified_name == "SUB",
    ).one()
    # Regressionstest fuer den beim Implementieren gefundenen Bug: ohne
    # ID-Erhalt beim Reparse waere SUB neu angelegt und die alte Zeile (samt
    # der CALL-Kante aus MAIN, die per CASCADE an ihr haengt) verschwunden.
    assert sub_after.id == sub_before.id

    call_edge_after = db_session.query(CodeEdge).filter(
        CodeEdge.source_id == test_source.id, CodeEdge.type == "CALL",
    ).one()
    assert call_edge_after.id == call_edge_before.id
    assert call_edge_after.dst_entity_id == sub_before.id
    assert call_edge_after.resolution == "resolved"

    # Der neue Paragraph in SUB ist jetzt da.
    assert db_session.query(CodeEntity).filter(
        CodeEntity.source_id == test_source.id, CodeEntity.qualified_name == "SUB.EXTRA-PARA",
    ).one_or_none() is not None


@pytest.mark.anyio
async def test_removed_paragraph_entity_is_deleted_on_reparse(db_session, test_source, git_remote):
    await _sync(test_source.id)

    assert db_session.query(CodeEntity).filter(
        CodeEntity.source_id == test_source.id, CodeEntity.qualified_name == "MAIN.SUB-PARA",
    ).one_or_none() is not None

    _commit_file(
        git_remote, "MAIN.CBL",
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. MAIN.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n",
        "remove sub-para and copy/call",
    )
    await _sync(test_source.id)

    db_session.expire_all()
    assert db_session.query(CodeEntity).filter(
        CodeEntity.source_id == test_source.id, CodeEntity.qualified_name == "MAIN.SUB-PARA",
    ).one_or_none() is None
    assert db_session.query(CodeEntity).filter(
        CodeEntity.source_id == test_source.id, CodeEntity.qualified_name == "MAIN.MAIN-PARA",
    ).one_or_none() is not None
