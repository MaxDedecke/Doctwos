"""Abbruchtests für den Git-Import: Was bleibt nach einem Absturz mitten im Sync?

Ein echter Absturz (OOM, SIGKILL, Container-Neustart) führt keinen
``except``-Block mehr aus. ``SimulatedCrash`` erbt deshalb von
``BaseException``: Die Fehlerbehandlung des Connectors (``except Exception``)
greift nicht, die offene Transaktion geht verloren, der Status bleibt wie er ist.

Geprüft wird an mehreren Abbruchstellen zweierlei:

1. Der Zwischenstand direkt nach dem Absturz ist in sich konsistent: keine
   doppelten Entities oder Kanten, keine Kante mit totem Ziel, jede Datei steht
   vollständig auf genau einer Revision (Entities, Chunks und Journal stimmen
   überein), und der Sync-Cursor zeigt noch auf den alten Commit.
2. Nach dem Wiederaufsetzen entspricht der Bestand Feld für Feld einem
   ununterbrochenen Import desselben Repositorys.
"""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import aliased

import connectors.git as git_connector
import tasks.edge_resolver as edge_resolver
from connectors.git import GitConnector
from db import SessionLocal
from doctus_models.database import (
    CodeEdge,
    CodeEntity,
    DocumentChunk,
    KnowledgeSource,
    SourceScanFile,
)

SHARED_CONTAINERS = {"package", "module"}


class SimulatedCrash(BaseException):
    """Wie ein Prozessabbruch: wird von keinem ``except Exception`` abgefangen."""


def _git(repo: str, *args: str) -> None:
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _write(repo: str, rel_path: str, content: str) -> None:
    full_path = os.path.join(repo, rel_path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _commit(repo: str, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)


V1_FILES = {
    "src/main/java/com/acme/PaymentService.java": (
        "package com.acme;\npublic class PaymentService {\n    public void charge() {}\n}\n"
    ),
    "src/main/java/com/acme/PaymentClient.java": (
        "package com.acme;\nclass PaymentClient {\n"
        "    void pay() { new PaymentService().charge(); }\n}\n"
    ),
    "src/main/java/com/acme/Legacy.java": "package com.acme; class Legacy { void old() {} }\n",
    "src/main/cobol/PAYMENT.cbl": (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. PAYMENT.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       COPY PAYREC.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           CALL 'AUDIT'.\n"
        "           STOP RUN.\n"
    ),
    "src/main/cobol/AUDIT.cbl": (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. AUDIT.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           DISPLAY 'AUDIT'.\n"
        "           GOBACK.\n"
    ),
    "src/main/cpy/PAYREC.cpy": "       01 PAY-RECORD.\n          05 PAY-AMOUNT PIC 9(7)V99.\n",
}


def _apply_v2(repo: str) -> None:
    """Geänderte, neue und gelöschte Dateien in einem Commit."""
    _write(
        repo,
        "src/main/java/com/acme/PaymentClient.java",
        "package com.acme;\nclass PaymentClient {\n"
        "    void pay() { new PaymentService().charge(); }\n"
        "    void refund() { new PaymentService().charge(); }\n}\n",
    )
    _write(
        repo,
        "src/main/java/com/acme/PaymentReport.java",
        "package com.acme;\nclass PaymentReport {\n"
        "    void print() { new PaymentService().charge(); }\n}\n",
    )
    _write(
        repo,
        "src/main/cobol/AUDIT.cbl",
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. AUDIT.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           DISPLAY 'AUDIT V2'.\n"
        "           PERFORM CLOSE-PARA.\n"
        "           GOBACK.\n"
        "       CLOSE-PARA.\n"
        "           DISPLAY 'DONE'.\n",
    )
    os.remove(os.path.join(repo, "src/main/java/com/acme/Legacy.java"))
    _commit(repo, "v2")


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def remote(tmp_path):
    path = str(tmp_path / "crash-remote.git")
    subprocess.run(["git", "init", "--initial-branch=main", path], check=True, capture_output=True)
    _git(path, "config", "user.email", "test@doctus.local")
    _git(path, "config", "user.name", "Doctus Test")
    for rel_path, content in V1_FILES.items():
        _write(path, rel_path, content)
    _commit(path, "v1")
    return path


@pytest.fixture
def make_source(tmp_path, monkeypatch, db_session):
    monkeypatch.setattr("connectors.git.REPOS_ROOT", str(tmp_path / "repos"))
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": f"crash-team-{tmp_path.name}"},
    ).scalar_one()
    db_session.commit()
    created: list[tuple[int, int]] = []

    def create(url: str, label: str) -> int:
        project_id = db_session.execute(
            text(
                "INSERT INTO projects (name, team_id, created_at) "
                "VALUES (:name, :team_id, now()) RETURNING id"
            ),
            {"name": f"crash-{label}-{tmp_path.name}", "team_id": team_id},
        ).scalar_one()
        source = KnowledgeSource(
            name=f"Crash {label} {tmp_path.name}",
            type="Git",
            url=url,
            branch="main",
            project_id=project_id,
            team_id=team_id,
            spaces={"language_extensions": {"java": [".java"]}},
        )
        db_session.add(source)
        db_session.commit()
        created.append((source.id, project_id))
        return source.id

    yield create

    db_session.rollback()
    for source_id, project_id in created:
        for model in (CodeEdge, CodeEntity, SourceScanFile, DocumentChunk):
            db_session.query(model).filter(model.source_id == source_id).delete(
                synchronize_session=False
            )
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).delete(
            synchronize_session=False
        )
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


async def _sync(source_id: int, *faults) -> None:
    connector = GitConnector(source_id)
    patches = _embedding_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        for fault in faults:
            fault.start()
        try:
            await connector.sync()
        finally:
            for fault in faults:
                fault.stop()


def _source(db, source_id: int) -> KnowledgeSource:
    db.expire_all()
    return db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).one()


# ── Abbruchstellen ────────────────────────────────────────────────────────────


def _crash_after_persisting(path: str):
    """Entities und Kanten der Datei sind geschrieben (flush), der Commit fehlt."""
    real = git_connector.persist_parse_result

    def persist(db, **kwargs):
        stats = real(db, **kwargs)
        if kwargs["file_path"] == path:
            raise SimulatedCrash(f"nach Entities/Kanten von {path}")
        return stats

    return patch("connectors.git.persist_parse_result", side_effect=persist)


def _crash_before_persisting(path: str):
    """Andere Dateien sind schon committet, diese noch nicht begonnen."""
    real = git_connector.persist_parse_result

    def persist(db, **kwargs):
        if kwargs["file_path"] == path:
            raise SimulatedCrash(f"vor {path}")
        return real(db, **kwargs)

    return patch("connectors.git.persist_parse_result", side_effect=persist)


def _crash_while_deleting(path: str):
    real = git_connector._delete_file_entities

    def delete(db, *, source_id, file_path):
        real(db, source_id=source_id, file_path=file_path)
        if file_path == path:
            raise SimulatedCrash(f"beim Löschen von {path}")

    return patch("connectors.git._delete_file_entities", side_effect=delete)


def _crash_in_pass_two():
    """Frühere Auflöser haben die Session schon verändert; der Commit von Pass 2 fehlt."""

    def crash(db, source_id):
        raise SimulatedCrash("mitten in Pass 2")

    return patch.object(edge_resolver, "_resolve_jcl_edges", side_effect=crash)


def _crash_after_pass_two():
    """Pass 2 ist committet, Cursor und Abschlussstatus noch nicht."""

    def crash(db, source):
        raise SimulatedCrash("nach Pass 2")

    return patch("connectors.git.mark_source_insights_outdated", side_effect=crash)


FAULTS = {
    "nach_entities_vor_commit": lambda: _crash_after_persisting(
        "src/main/java/com/acme/PaymentClient.java"
    ),
    "zwischen_dateien": lambda: _crash_before_persisting(
        "src/main/java/com/acme/PaymentReport.java"
    ),
    "beim_loeschen": lambda: _crash_while_deleting("src/main/java/com/acme/Legacy.java"),
    "in_pass_2": _crash_in_pass_two,
    "nach_pass_2": _crash_after_pass_two,
}


# ── Invarianten und Vergleich ─────────────────────────────────────────────────


def _assert_consistent(db, source_id: int) -> None:
    entities = db.query(CodeEntity).filter(CodeEntity.source_id == source_id).all()
    edges = db.query(CodeEdge).filter(CodeEdge.source_id == source_id).all()
    journal = {
        row.file_path: row
        for row in db.query(SourceScanFile).filter(SourceScanFile.source_id == source_id)
    }
    chunks = db.query(DocumentChunk).filter(DocumentChunk.source_id == source_id).all()
    entity_ids = {entity.id for entity in entities}

    duplicates = Counter(
        (e.variant_key, e.file_path, e.qualified_name) for e in entities
    ).most_common(1)
    assert not duplicates or duplicates[0][1] == 1, f"doppelte Entity: {duplicates}"
    edge_keys = Counter(
        (e.variant_key, e.src_entity_id, e.type, e.dst_name, e.src_start_line) for e in edges
    ).most_common(1)
    assert not edge_keys or edge_keys[0][1] == 1, f"doppelte Kante: {edge_keys}"

    for edge in edges:
        assert edge.src_entity_id in entity_ids, f"Kante ohne Quelle: {edge.dst_name}"
        if edge.dst_entity_id is not None:
            assert edge.dst_entity_id in entity_ids, f"Kante mit totem Ziel: {edge.dst_name}"
        if edge.resolution == "resolved":
            assert edge.dst_entity_id is not None, f"aufgelöst ohne Ziel: {edge.dst_name}"

    # Jede Datei steht vollständig auf genau einer Revision: Entities, Chunks
    # und Journal tragen denselben Inhalts-Hash.
    for entity in entities:
        if entity.type in SHARED_CONTAINERS:
            continue
        record = journal.get(entity.file_path)
        assert record is not None, f"Entity ohne Journal: {entity.file_path}"
        assert entity.content_hash == record.content_hash, (
            f"gemischte Revision in {entity.file_path}: "
            f"Entity {entity.qualified_name} {entity.content_hash} != {record.content_hash}"
        )
    for chunk in chunks:
        record = journal.get(chunk.file_path)
        assert record is not None, f"Chunk ohne Journal: {chunk.file_path}"
        chunk_hash = (chunk.metadata_json or {}).get("content_hash")
        assert chunk_hash == record.content_hash, f"gemischte Revision in {chunk.file_path}"


def _snapshot(db, source_id: int) -> dict[str, set]:
    """Inhalt ohne Datenbank-IDs, damit zwei Quellen vergleichbar sind."""
    src = aliased(CodeEntity)
    dst = aliased(CodeEntity)
    parent = aliased(CodeEntity)
    return {
        "entities": {
            (
                None if e.type in SHARED_CONTAINERS else e.file_path,
                e.qualified_name,
                e.type,
                e.start_line,
                e.end_line,
                None if e.type in SHARED_CONTAINERS else e.content_hash,
                parent_qname,
            )
            for e, parent_qname in db.query(CodeEntity, parent.qualified_name)
            .outerjoin(parent, CodeEntity.parent_id == parent.id)
            .filter(CodeEntity.source_id == source_id)
        },
        "edges": {
            (
                src_file,
                src_qname,
                edge.type,
                edge.dst_name,
                edge.resolution,
                dst_qname,
                edge.src_start_line,
                edge.src_end_line,
            )
            for edge, src_file, src_qname, dst_qname in db.query(
                CodeEdge, src.file_path, src.qualified_name, dst.qualified_name
            )
            .join(src, CodeEdge.src_entity_id == src.id)
            .outerjoin(dst, CodeEdge.dst_entity_id == dst.id)
            .filter(CodeEdge.source_id == source_id)
        },
        "journal": {
            (row.file_path, row.content_hash, row.parse_status, row.language)
            for row in db.query(SourceScanFile).filter(SourceScanFile.source_id == source_id)
        },
        "chunks": {
            (chunk.file_path, chunk.start_line, chunk.end_line, chunk.content)
            for chunk in db.query(DocumentChunk).filter(DocumentChunk.source_id == source_id)
        },
    }


def _assert_same(actual: dict[str, set], expected: dict[str, set]) -> None:
    for key in expected:
        missing = expected[key] - actual[key]
        extra = actual[key] - expected[key]
        assert not missing and not extra, (
            f"{key}: fehlt {sorted(missing, key=str)[:5]}, zu viel {sorted(extra, key=str)[:5]}"
        )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
@pytest.mark.parametrize("fault", sorted(FAULTS))
async def test_crash_leaves_a_consistent_index_and_resume_matches_an_uninterrupted_import(
    db_session, remote, make_source, fault
):
    reference_id = make_source(remote, "referenz")
    source_id = make_source(remote, "abbruch")
    await _sync(source_id)
    v1_commit = _source(db_session, source_id).sync_cursor["last_commit"]
    _assert_consistent(db_session, source_id)

    _apply_v2(remote)
    await _sync(reference_id)
    assert _source(db_session, reference_id).sync_status == "completed"
    expected = _snapshot(db_session, reference_id)

    with pytest.raises(SimulatedCrash):
        await _sync(source_id, FAULTS[fault]())

    crashed = _source(db_session, source_id)
    assert crashed.sync_status == "syncing", "ein Absturz darf nicht als fertig gelten"
    assert crashed.sync_cursor["last_commit"] == v1_commit
    _assert_consistent(db_session, source_id)

    await _sync(source_id)
    resumed = _source(db_session, source_id)
    assert resumed.sync_status == "completed"
    assert resumed.sync_cursor["last_commit"] != v1_commit
    _assert_consistent(db_session, source_id)
    _assert_same(_snapshot(db_session, source_id), expected)


@pytest.mark.anyio
async def test_a_log_line_from_a_parallel_task_cannot_split_a_file_write(
    db_session, remote, make_source
):
    """Parallele Tasks loggen über dieselbe Session. Ein Commit aus ``_log`` mitten
    im Schreiben einer Datei würde Entities ohne Chunks und Journal festschreiben."""
    source_id = make_source(remote, "log")
    await _sync(source_id)
    _apply_v2(remote)

    connector = GitConnector(source_id)
    real = git_connector.persist_parse_result

    def persist(db, **kwargs):
        stats = real(db, **kwargs)
        if kwargs["file_path"] == "src/main/java/com/acme/PaymentClient.java":
            connector._log("Zeile eines parallelen Embedding-Tasks")
            connector._update_progress(1, 2, "parallel")
            raise SimulatedCrash("nach Log-Zeile mitten im Schreiben")
        return stats

    patches = _embedding_patches()
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patch("connectors.git.persist_parse_result", side_effect=persist),
        pytest.raises(SimulatedCrash),
    ):
        await connector.sync()

    _assert_consistent(db_session, source_id)
