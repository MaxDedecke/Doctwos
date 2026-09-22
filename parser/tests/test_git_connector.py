import asyncio
import os
import subprocess
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from unittest.mock import AsyncMock, patch

from cobol.model import Chunk, ParseResult
from cobol.profile import BuildProfile, SourceColumns
from core.analysis_fingerprint import analysis_fingerprint
from core import config
from core.registry import ParserEntry, STRUCTURE_PARSERS
from db import SessionLocal
from models.database import CodeEntity, KnowledgeSource, SourceScanFile, DocumentChunk
from connectors.git import (
    GitConnector,
    _looks_like_text,
    _resolve_document_profile,
    _resolve_extension_config,
    _reuse_unchanged_embeddings,
    _run_prepare_hooks,
    _is_java_build_excluded,
    classify_extension,
)
import git_utils


async def _run_to_thread_inline(func, *args, **kwargs):
    """Keep dispatch-contract tests independent of executor shutdown behavior."""
    return func(*args, **kwargs)


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


def test_resolve_extension_config_reads_new_language_extensions_key():
    """O-078: `spaces.cobol_extensions` wurde in `language_extensions`
    umbenannt (der Schlüssel selbst tut nichts COBOL-Spezifisches)."""
    cfg = _resolve_extension_config({"language_extensions": {"cobol": [".foo"]}})
    assert cfg["cobol"] == {".foo"}


def test_resolve_extension_config_still_reads_old_cobol_extensions_key():
    """Rückwärtskompatibilität: bestehende Wissensquellen mit gespeicherter
    Alt-Konfiguration (`cobol_extensions`) dürfen nicht brechen."""
    cfg = _resolve_extension_config({"cobol_extensions": {"cobol": [".bar"]}})
    assert cfg["cobol"] == {".bar"}


def test_resolve_extension_config_prefers_new_key_over_old():
    cfg = _resolve_extension_config(
        {"language_extensions": {"cobol": [".new"]}, "cobol_extensions": {"cobol": [".old"]}}
    )
    assert cfg["cobol"] == {".new"}


def test_common_programming_languages_are_detected_by_default(monkeypatch):
    monkeypatch.delenv("DOCTUS_LANGUAGE_EXTENSIONS", raising=False)
    monkeypatch.delenv("DOCTUS_COBOL_EXTENSIONS", raising=False)
    defaults = _resolve_extension_config({})

    assert classify_extension("src/App.java", defaults) == "java"
    assert classify_extension("src/main.kt", defaults) == "kotlin"
    assert classify_extension("src/main.py", defaults) == "python"
    assert classify_extension("src/main.ts", defaults) == "typescript"
    assert classify_extension("web/templates/page.html", defaults) == "html"
    assert classify_extension("web/templates/page.jspx", defaults) == "jsp"
    assert classify_extension("web/styles/main.xslt", defaults) == "xslt"
    assert classify_extension("config/application.properties", defaults) == "properties"
    assert classify_extension("build/pom.xml", defaults) == "maven"
    assert classify_extension("README.md", defaults) == "text"


def test_extensionless_shell_script_is_detected_from_bounded_shebang(monkeypatch):
    monkeypatch.delenv("DOCTUS_LANGUAGE_EXTENSIONS", raising=False)
    monkeypatch.delenv("DOCTUS_COBOL_EXTENSIONS", raising=False)
    defaults = _resolve_extension_config({})

    assert classify_extension("bin/start", defaults, "#!/usr/bin/env bash\nset -eu\n") == "shell"
    assert classify_extension("bin/start", defaults, "#!/usr/bin/python3\nprint('x')\n") == "text"


def test_custom_language_extension_can_be_added_worker_wide(monkeypatch):
    monkeypatch.delenv("DOCTUS_COBOL_EXTENSIONS", raising=False)
    monkeypatch.setenv("DOCTUS_LANGUAGE_EXTENSIONS", '{"python": [".python-source"]}')
    cfg = _resolve_extension_config({})

    assert classify_extension("src/tool.python-source", cfg) == "python"


def test_java_build_directory_excludes_are_scoped_to_java_sources(monkeypatch):
    monkeypatch.delenv("DOCTUS_LANGUAGE_EXTENSIONS", raising=False)
    monkeypatch.delenv("DOCTUS_COBOL_EXTENSIONS", raising=False)
    opted_in = _resolve_extension_config({"language_extensions": {"java": [".java"]}})

    assert _is_java_build_excluded("module/target/generated/App.java", opted_in)
    assert _is_java_build_excluded("module/.gradle/cache/App.java", opted_in)
    assert not _is_java_build_excluded("module/src/main/java/App.java", opted_in)
    assert not _is_java_build_excluded("target/MAIN.cbl", opted_in)


def test_resolve_document_profile_uses_the_most_specific_path_override():
    profile = _resolve_document_profile(
        {
            "build_profile": {
                "source": {"compiler_family": "GNUCOBOL", "source_format": "fixed"},
                "paths": {
                    "legacy": {"source_format": "free"},
                    "legacy/payroll": {"compiler_version": "4.0"},
                },
            }
        },
        "legacy/payroll/MAIN.CBL",
    )

    assert profile == BuildProfile(
        compiler_family="GNUCOBOL",
        compiler_version="4.0",
        source_format="fixed",
        resolved_from={
            "compiler_family": "source",
            "compiler_version": "path",
            "source_format": "source",
        },
    )


def test_resolve_document_profile_reads_configured_source_columns():
    profile = _resolve_document_profile(
        {
            "build_profile": {
                "source": {
                    "source_format": "variable",
                    "source_columns": {"code_end": 180},
                }
            }
        },
        "MAIN.CBL",
    )

    assert profile == BuildProfile(
        source_format="variable",
        source_columns=SourceColumns(code_end=180),
        resolved_from={"source_format": "source", "source_columns": "source"},
    )


def test_resolve_document_profile_reads_debug_mode():
    profile = _resolve_document_profile(
        {"build_profile": {"source": {"source_format": "fixed", "debug_mode": True}}},
        "MAIN.CBL",
    )

    assert profile == BuildProfile(
        source_format="fixed",
        debug_mode=True,
        resolved_from={"source_format": "source", "debug_mode": "source"},
    )


def test_resolve_document_profile_reads_literal_delimiter():
    profile = _resolve_document_profile(
        {"build_profile": {"source": {"literal_delimiter": "apostrophe"}}},
        "MAIN.CBL",
    )

    assert profile == BuildProfile(
        literal_delimiter="apostrophe",
        resolved_from={"literal_delimiter": "source"},
    )


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
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"
        ),
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
        patch(
            "connectors.git.get_embeddings_batch",
            AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts]),
        ),
        patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)),
        # O-071: ohne Patch würde is_gpu_accelerated() bei jedem Testlauf einen
        # echten Ollama-Aufruf versuchen; True haelt die bisherige volle
        # EMBED_CONCURRENCY bei, damit diese Tests unveraendert bleiben.
        patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)),
    )


@pytest.mark.anyio
async def test_markup_budget_and_duplicate_shell_entities_survive_git_ingestion(
    db_session, test_source, git_remote
):
    _commit_file(
        git_remote,
        ".setup/pipeline-common.sh",
        "print_phase_next_step() { echo first; }\nprint_phase_next_step() { echo second; }\n",
        "Repeated shell function",
    )
    _commit_file(
        git_remote, "large.html", "<script>" + "ä漢😀" * 4000 + "</script>", "Large UTF-8 markup"
    )
    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with (
        p1,
        p2 as batch,
        p3,
        p4,
        patch("connectors.git.get_embedding_input_budget", return_value=128),
    ):
        await connector.sync()
    db_session.refresh(test_source)
    assert test_source.sync_status == "completed", test_source.last_error
    markup_batches = [
        call.args[0] for call in batch.call_args_list if any("😀" in item for item in call.args[0])
    ]
    assert markup_batches
    assert all(len(item.encode("utf-8")) <= 128 for items in markup_batches for item in items)
    functions = (
        db_session.query(CodeEntity)
        .filter_by(source_id=test_source.id, type="shell_function")
        .all()
    )
    assert len(functions) == 2
    assert len({item.qualified_name for item in functions}) == 2
    assert {item.start_line for item in functions} == {1, 2}
    assert (
        db_session.query(DocumentChunk)
        .filter_by(source_id=test_source.id, file_path="large.html")
        .count()
        > 1
    )


@pytest.mark.anyio
async def test_persistence_failure_is_visible_and_does_not_commit_chunks(db_session, test_source):
    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with (
        p1,
        p2,
        p3,
        p4,
        patch("connectors.git.persist_parse_result", side_effect=ValueError("duplicate entity")),
    ):
        await connector.sync()
    db_session.refresh(test_source)
    assert test_source.sync_status == "error"
    scan = (
        db_session.query(SourceScanFile)
        .filter_by(source_id=test_source.id, file_path="PROG.CBL")
        .one()
    )
    assert scan.parse_status == "error"
    assert "duplicate entity" in scan.parse_error
    assert "'PROG.CBL' indexiert" not in test_source.sync_log
    assert (
        db_session.query(DocumentChunk)
        .filter_by(source_id=test_source.id, file_path="PROG.CBL")
        .count()
        == 0
    )
    assert (
        db_session.query(DocumentChunk)
        .filter_by(source_id=test_source.id, file_path="README.md")
        .count()
        > 0
    )


@pytest.mark.anyio
async def test_failed_embedding_keeps_previous_file_revision(db_session, test_source, git_remote):
    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()
    old_chunks = (
        db_session.query(DocumentChunk)
        .filter_by(source_id=test_source.id, file_path="README.md")
        .all()
    )
    old_ids = {item.id for item in old_chunks}
    assert old_ids
    _commit_file(
        git_remote,
        "README.md",
        "Changed documentation that must not replace the last working revision.\n" * 100,
        "Change docs",
    )
    connector = GitConnector(test_source.id)
    p1, _, _, p4 = _patched_sync(connector)
    with (
        p1,
        p4,
        patch("connectors.git.get_embeddings_batch", AsyncMock(side_effect=ValueError("offline"))),
        patch(
            "connectors.git.get_embedding",
            AsyncMock(side_effect=[[0.1] * 1024, ValueError("offline")]),
        ),
    ):
        await connector.sync()
    db_session.expire_all()
    assert {
        item.id
        for item in db_session.query(DocumentChunk).filter_by(
            source_id=test_source.id, file_path="README.md"
        )
    } == old_ids
    assert (
        db_session.query(SourceScanFile)
        .filter_by(source_id=test_source.id, file_path="README.md")
        .one()
        .parse_status
        == "error"
    )
    assert test_source.sync_status == "error"


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
        r.file_path: r
        for r in db_session.query(SourceScanFile)
        .filter(SourceScanFile.source_id == test_source.id)
        .all()
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
async def test_git_connector_classifies_every_file_by_its_own_extension(
    db_session, test_source, git_remote
):
    """
    Regression (O-176): `fetch_documents()` computes `language` once per file
    while building `to_process` (for the O-122 analysis fingerprint), but
    only stored (path, content_hash, fingerprint) in that list -- not
    `language` itself. The processing loop below then read the very same,
    still-in-scope `language` variable (Python has no block scope), which by
    then held whatever the ALPHABETICALLY LAST path in the whole repo had
    classified to, for every single file, regardless of its own extension.

    Live at CardDemo: the last sorted path was 'scripts/upld_module.sh'
    ("text"), so every COBOL/copybook file in the 300+-file repo -- no
    matter its own extension -- got embedded with language="text":
    STRUCTURE_PARSERS never matched, parse_result stayed None,
    persist_parse_result() never ran, and code_entities/code_edges stayed
    completely empty for the whole source (0 rows, reproduced against the
    real database).

    Here: 'AAAMAIN.CBL' sorts before 'zzz_trailing.sh' -- the exact ordering
    that triggers the bug (a COBOL file is not the alphabetically-last path).
    """
    cobol_source = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. AAAMAIN.\n"
        "       PROCEDURE DIVISION.\n"
        "       0000-MAIN.\n"
        "           STOP RUN.\n"
    )
    _commit_file(git_remote, "AAAMAIN.CBL", cobol_source, "add cobol program")
    _commit_file(git_remote, "zzz_trailing.sh", "#!/bin/sh\necho hi\n", "add trailing text file")

    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"

    cobol_chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == "AAAMAIN.CBL")
        .all()
    )
    assert cobol_chunks and all(c.metadata_json.get("language") == "cobol" for c in cobol_chunks)

    entities = (
        db_session.query(CodeEntity)
        .filter(CodeEntity.source_id == test_source.id, CodeEntity.file_path == "AAAMAIN.CBL")
        .all()
    )
    assert any(e.type == "program" and e.name == "AAAMAIN" for e in entities)

    scan_file = (
        db_session.query(SourceScanFile)
        .filter(
            SourceScanFile.source_id == test_source.id, SourceScanFile.file_path == "AAAMAIN.CBL"
        )
        .first()
    )
    assert scan_file is not None
    assert scan_file.parse_status in ("complete", "partial")


@pytest.mark.anyio
async def test_git_connector_parses_java_without_source_setting(db_session, test_source):
    _commit_file(
        test_source.url,
        "src/demo/App.java",
        "package demo;\npublic class App { public void run() {} }\n",
        "add java source",
    )
    _commit_file(
        test_source.url,
        "target/generated/Generated.java",
        "package generated; class Generated {}\n",
        "add generated java source",
    )

    connector = GitConnector(test_source.id)
    patches = _patched_sync(connector)
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "src/demo/App.java",
        )
        .all()
    )
    entities = (
        db_session.query(CodeEntity)
        .filter(
            CodeEntity.source_id == test_source.id,
            CodeEntity.file_path == "src/demo/App.java",
        )
        .all()
    )

    assert chunks
    assert all(chunk.metadata_json.get("language") == "java" for chunk in chunks)
    assert any(chunk.metadata_json.get("symbol_type") == "method" for chunk in chunks)
    assert {entity.type for entity in entities} >= {
        "compilation_unit",
        "package",
        "class",
        "method",
    }
    assert not (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "target/generated/Generated.java",
        )
        .all()
    )


@pytest.mark.anyio
async def test_git_connector_delta_sync_add_modify_delete(db_session, test_source, git_remote):
    connector1 = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector1)
    with p1, p2, p3, p4:
        await connector1.sync()

    # Remote aendert sich: PROG.CBL modifiziert, README.md geloescht, NEW.CBL neu
    _commit_file(
        git_remote, "PROG.CBL", "IDENTIFICATION DIVISION.\nPROGRAM-ID. PROG.\nMORE.\n", "update"
    )
    _delete_file(git_remote, "README.md", "remove readme")
    _commit_file(git_remote, "NEW.CBL", "IDENTIFICATION DIVISION.\nPROGRAM-ID. NEW.\n", "add new")

    connector2 = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector2)
    with p1, p2, p3, p4:
        await connector2.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"

    scan_paths = {
        r.file_path
        for r in db_session.query(SourceScanFile)
        .filter(SourceScanFile.source_id == test_source.id)
        .all()
    }
    assert scan_paths == {"PROG.CBL", "NEW.CBL"}

    chunk_paths = {
        c.file_path
        for c in db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id)
        .all()
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

    connector = GitConnector(test_source.id)
    with (
        patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)),
        patch(
            "connectors.git.get_embeddings_batch",
            AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts]),
        ),
        patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)),
        patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)),
    ):
        await connector.sync(force_reindex=True)

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    # O-122 reuses embeddings for text-identical chunks even during a forced
    # analysis; force_reindex guarantees that every file is processed again.
    assert test_source.parsed_files == test_source.total_files > 0


@pytest.mark.anyio
async def test_git_connector_reembeds_all_files_when_embedding_model_changes(
    db_session, test_source
):
    """O-252: a model change must not be hidden by the content fingerprint."""
    connector = GitConnector(test_source.id)
    patches = _patched_sync(connector)
    with patches[0], patches[1], patches[2], patches[3]:
        await connector.sync()

    before = {
        row.file_path: row.analysis_fingerprint
        for row in db_session.query(SourceScanFile)
        .filter(SourceScanFile.source_id == test_source.id)
        .all()
    }
    test_source.embedding_model = "replacement-embedding-model"
    db_session.commit()

    connector = GitConnector(test_source.id)
    p1, embed_batch, p3, p4 = _patched_sync(connector)
    with p1, embed_batch as embed_batch_mock, p3, p4:
        await connector.sync()

    assert embed_batch_mock.await_count > 0
    assert all(
        call.kwargs.get("model") == "replacement-embedding-model"
        for call in embed_batch_mock.call_args_list
    )
    after = {
        row.file_path: row.analysis_fingerprint
        for row in db_session.query(SourceScanFile)
        .filter(SourceScanFile.source_id == test_source.id)
        .all()
    }
    assert after["PROG.CBL"] != before["PROG.CBL"]
    assert after["README.md"] != before["README.md"]
    assert {
        chunk.embedding_model
        for chunk in db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id)
        .all()
    } == {"replacement-embedding-model"}


@pytest.mark.anyio
async def test_git_connector_resumes_via_content_hash(
    db_session, test_source, monkeypatch, tmp_path
):
    """O-122/NF-004: nur ein vollständiger Analyse-Fingerprint darf einen
    bereits fertigen Parse wiederaufnehmen; eine bloße Altzeile ohne diesen
    Wert wird bewusst einmal neu verarbeitet."""
    repos_root = str(tmp_path / "repos_root")
    monkeypatch.setattr("connectors.git.REPOS_ROOT", repos_root)

    fp = git_utils.compute_repo_fingerprint(test_source.url)
    bare = git_utils.ensure_bare_mirror(repos_root, fp, test_source.url)
    git_utils.fetch_branch(bare, "main")
    wt = git_utils.worktree_path(repos_root, test_source.id)
    git_utils.ensure_worktree(bare, wt, "main")
    tracked = git_utils.list_tracked_files(wt)

    db_session.add(
        SourceScanFile(
            source_id=test_source.id,
            file_path="PROG.CBL",
            content_hash=git_utils.blob_content_hash(tracked["PROG.CBL"]),
            language="cobol",
            parse_status="complete",
            analysis_fingerprint=analysis_fingerprint(
                source_revision=tracked["PROG.CBL"],
                profile=BuildProfile(),
                parser_version="cobol-structure-3",
                grammar_version=STRUCTURE_PARSERS["cobol"].grammar_fingerprint(),
                libraries={},
                embedding_model=config.EMBED_MODEL,
            ),
        )
    )
    db_session.commit()

    connector = GitConnector(test_source.id)
    embed_batch = AsyncMock(side_effect=lambda texts, model=None: [[0.1] * 1024 for _ in texts])
    with (
        patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)),
        patch("connectors.git.get_embeddings_batch", embed_batch),
        patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)),
        patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)),
    ):
        await connector.sync()

    embedded_titles = [call.args[0] for call in embed_batch.call_args_list]
    # PROG.CBL's einziger Chunk darf nie an get_embeddings_batch gegangen sein
    combined_texts = [t for batch in embedded_titles for t in batch]
    assert not any("PROGRAM-ID. PROG." in t for t in combined_texts)

    chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "PROG.CBL",
        )
        .all()
    )
    # Kein neuer Chunk fuer die uebersprungene Datei angelegt
    assert len(chunks) == 0


@pytest.mark.anyio
async def test_git_connector_shares_bare_mirror_across_sources(
    db_session, git_remote, tmp_path, monkeypatch
):
    repos_root = str(tmp_path / "repos_root")
    monkeypatch.setattr("connectors.git.REPOS_ROOT", repos_root)

    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "git-share-team"},
    ).scalar_one()
    project_a = db_session.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"
        ),
        {"name": "git-share-project-a", "team_id": team_id},
    ).scalar_one()
    project_b = db_session.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"
        ),
        {"name": "git-share-project-b", "team_id": team_id},
    ).scalar_one()

    source_a = KnowledgeSource(
        name="A", type="Git", url=git_remote, branch="main", project_id=project_a, team_id=team_id
    )
    source_b = KnowledgeSource(
        name="B", type="Git", url=git_remote, branch="main", project_id=project_b, team_id=team_id
    )
    db_session.add_all([source_a, source_b])
    db_session.commit()
    db_session.refresh(source_a)
    db_session.refresh(source_b)

    try:
        for src in (source_a, source_b):
            connector = GitConnector(src.id)
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
        db_session.query(SourceScanFile).filter(
            SourceScanFile.source_id.in_([source_a.id, source_b.id])
        ).delete(synchronize_session=False)
        db_session.query(DocumentChunk).filter(
            DocumentChunk.source_id.in_([source_a.id, source_b.id])
        ).delete(synchronize_session=False)
        db_session.delete(source_a)
        db_session.delete(source_b)
        db_session.execute(
            text("DELETE FROM projects WHERE id IN (:a, :b)"), {"a": project_a, "b": project_b}
        )
        db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
        db_session.commit()


@pytest.mark.anyio
async def test_git_connector_falls_back_to_per_chunk_embedding_and_logs_a_useful_error(
    db_session, test_source
):
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
    with (
        patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)),
        patch("connectors.git.get_embeddings_batch", AsyncMock(side_effect=Exception())),
        patch("connectors.git.get_embedding", AsyncMock(return_value=[0.1] * 1024)),
        patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)),
    ):
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert "Embedding-Fehler für 'PROG.CBL': Exception:" in test_source.sync_log

    # The fallback still embedded and saved every chunk -- a failed batch
    # attempt must not silently drop a file's content.
    chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "PROG.CBL",
        )
        .all()
    )
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
    with (
        patch("connectors.git.ensure_model_pulled", AsyncMock(return_value=None)),
        patch("connectors.git.get_embeddings_batch", AsyncMock(side_effect=Exception())),
        patch(
            "connectors.git.get_embedding", AsyncMock(side_effect=ValueError("truncated response"))
        ),
        patch("connectors.git.is_gpu_accelerated", AsyncMock(return_value=True)),
    ):
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "error"
    assert (
        "Embedding-Fehler für 'PROG.CBL' (Chunk übersprungen): ValueError: truncated response"
        in test_source.sync_log
    )

    # Every chunk failed both attempts -- the file must not silently claim
    # success while carrying zero actual content.
    chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "PROG.CBL",
        )
        .all()
    )
    assert len(chunks) == 0

    scan = (
        db_session.query(SourceScanFile)
        .filter_by(source_id=test_source.id, file_path="PROG.CBL")
        .one()
    )
    assert scan.parse_status == "error"
    assert "Embedding unvollständig" in scan.parse_error
    assert "'PROG.CBL' indexiert (0 Chunks)" not in test_source.sync_log

    # A retry without a commit change must revisit the failed file.
    retry = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(retry)
    with p1, p2, p3, p4:
        await retry.sync()
    db_session.refresh(scan)
    db_session.refresh(test_source)
    assert scan.parse_status != "error"
    assert test_source.sync_status == "completed"


@pytest.mark.anyio
async def test_git_connector_draining_fetch_documents_alone_does_not_move_progress(
    db_session, test_source
):
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
    connector.source = (
        connector.db.query(KnowledgeSource).filter(KnowledgeSource.id == test_source.id).first()
    )

    docs = [doc async for doc in connector.fetch_documents()]
    assert len(docs) == 2  # PROG.CBL + README.md, from the git_remote fixture

    db_session.refresh(test_source)
    assert test_source.total_files == 2  # legitimately set during fetch_documents()
    assert test_source.parsed_files == 0
    assert test_source.progress == 0


@pytest.mark.anyio
async def test_git_connector_progress_advances_only_as_files_actually_complete(
    db_session, test_source
):
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
async def test_git_connector_skips_known_binary_formats_instead_of_embedding_garbage(
    db_session, test_source, git_remote
):
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
    _commit_file(
        git_remote,
        "diagrams/architecture.png",
        "not real PNG bytes, extension is what matters here",
        "add diagram",
    )

    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert "[SKIP] 'diagrams/architecture.png' ist ein Binärformat" in test_source.sync_log

    # The .png must never reach the embedding pipeline -- no chunk.
    chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "diagrams/architecture.png",
        )
        .all()
    )
    assert len(chunks) == 0
    # O-120: the skip IS recorded now (as its own "skipped" status) -- a
    # future sync must be able to tell "seen and deliberately skipped" apart
    # from "never seen", and the Editor/diagnostics bundle need something to
    # show for this file at all.
    scan_file = (
        db_session.query(SourceScanFile)
        .filter(
            SourceScanFile.source_id == test_source.id,
            SourceScanFile.file_path == "diagrams/architecture.png",
        )
        .first()
    )
    assert scan_file is not None
    assert scan_file.parse_status == "skipped"
    assert "Binärformat" in scan_file.parse_error
    assert scan_file.language == "binary"

    # The legitimate COBOL/Markdown files must still be processed normally --
    # this must not turn into a blanket skip.
    cobol_chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "PROG.CBL",
        )
        .all()
    )
    assert len(cobol_chunks) >= 1


@pytest.mark.anyio
async def test_git_connector_skips_non_utf8_content_despite_text_looking_extension(
    db_session, test_source, git_remote
):
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
    _commit_file(
        git_remote, "AWS.M2.CARDDEMO.ACCTDATA.PS", "placeholder", "add mainframe data file"
    )
    _commit_binary_file(
        git_remote, "AWS.M2.CARDDEMO.ACCTDATA.PS", ebcdic_digits, "overwrite with EBCDIC bytes"
    )

    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert "[SKIP] 'AWS.M2.CARDDEMO.ACCTDATA.PS' ist kein UTF-8-Text" in test_source.sync_log

    chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "AWS.M2.CARDDEMO.ACCTDATA.PS",
        )
        .all()
    )
    assert len(chunks) == 0
    scan_file = (
        db_session.query(SourceScanFile)
        .filter(
            SourceScanFile.source_id == test_source.id,
            SourceScanFile.file_path == "AWS.M2.CARDDEMO.ACCTDATA.PS",
        )
        .first()
    )
    assert scan_file is not None
    assert scan_file.parse_status == "skipped"
    assert "UTF-8" in scan_file.parse_error


@pytest.mark.anyio
async def test_git_connector_skips_empty_files_instead_of_indexing_zero_chunks(
    db_session, test_source, git_remote
):
    """
    Regression (O-175): live an CardDemo beobachtet -- `scripts/markers/`
    enthält 0-Byte-Platzhalterdateien, die denselben Basisnamen wie echte
    JCL/Copybooks tragen (CUSTFILE, CVTRA02Y, READCUST, ...), nur ohne
    Endung. looks_like_text() lässt leeren Inhalt bewusst durch (er ist kein
    Datenmüll), GitConnector hatte davor aber keinen eigenen Leer-Check wie
    folder.py/webdav.py ("[SKIP] Kein Textinhalt") -- das Dokument lief bis
    zum Chunking durch und landete nur als irreführendes "indexiert
    (0 Chunks)" im Sync-Log, unsichtbar für den O-120-skipped-Status.
    """
    _commit_file(git_remote, "scripts/markers/CUSTFILE", "", "add empty marker file")

    connector = GitConnector(test_source.id)
    p1, p2, p3, p4 = _patched_sync(connector)
    with p1, p2, p3, p4:
        await connector.sync()

    db_session.refresh(test_source)
    assert test_source.sync_status == "completed"
    assert "[SKIP] 'scripts/markers/CUSTFILE' ist leer" in test_source.sync_log
    assert "'scripts/markers/CUSTFILE' indexiert" not in test_source.sync_log

    chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "scripts/markers/CUSTFILE",
        )
        .all()
    )
    assert len(chunks) == 0
    scan_file = (
        db_session.query(SourceScanFile)
        .filter(
            SourceScanFile.source_id == test_source.id,
            SourceScanFile.file_path == "scripts/markers/CUSTFILE",
        )
        .first()
    )
    assert scan_file is not None
    assert scan_file.parse_status == "skipped"
    assert "leer" in scan_file.parse_error

    # Eine echte (nicht-leere) Datei mit demselben Basisnamen muss unverändert
    # normal indexiert werden -- kein blanket skip über den Namen.
    cobol_chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "PROG.CBL",
        )
        .all()
    )
    assert len(cobol_chunks) >= 1


@pytest.mark.anyio
async def test_git_connector_skips_valid_utf8_dominated_by_control_characters(
    db_session, test_source, git_remote
):
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
    assert "[SKIP] 'weird.dat' ist kein sinnvoller utf-8-Text" in test_source.sync_log
    chunks = (
        db_session.query(DocumentChunk)
        .filter(
            DocumentChunk.source_id == test_source.id,
            DocumentChunk.file_path == "weird.dat",
        )
        .all()
    )
    assert len(chunks) == 0
    scan_file = (
        db_session.query(SourceScanFile)
        .filter(SourceScanFile.source_id == test_source.id, SourceScanFile.file_path == "weird.dat")
        .first()
    )
    assert scan_file is not None
    assert scan_file.parse_status == "skipped"


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


@pytest.mark.anyio
async def test_run_prepare_hooks_dedupes_shared_hook_and_skips_languages_without_one():
    """O-079: `_run_prepare_hooks()` läuft generisch über STRUCTURE_PARSERS
    -- ein von mehreren Sprachen geteilter prepare_source-Hook (wie
    `prepare_copybook_index` für "cobol"/"copybook") läuft nur EINMAL statt
    einmal pro Sprache, und eine Sprache ohne Hook bekommt gar keinen
    Eintrag im Ergebnis (statt z. B. `None` vorzutäuschen)."""
    calls = []

    def shared_hook(wt, extensions, profiles_by_path):
        calls.append((wt, extensions, profiles_by_path))
        return "prepared-once"

    fake_registry = {
        "langA": ParserEntry(parse=lambda *a, **k: None, prepare_source=shared_hook),
        "langB": ParserEntry(parse=lambda *a, **k: None, prepare_source=shared_hook),
        "langC": ParserEntry(parse=lambda *a, **k: None),  # kein Hook
    }

    with (
        patch("connectors.git.STRUCTURE_PARSERS", fake_registry),
        patch("connectors.git.asyncio.to_thread", _run_to_thread_inline),
    ):
        prepared = await _run_prepare_hooks("/some/wt", {"ext": {".x"}})

    assert calls == [("/some/wt", {"ext": {".x"}}, {})]
    assert prepared == {"langA": "prepared-once", "langB": "prepared-once"}
    assert "langC" not in prepared


@pytest.mark.anyio
async def test_git_connector_dispatches_via_structure_parser_registry():
    """O-077: der Dispatch von Sprache -> Struktur-Parser läuft über
    connectors.git.STRUCTURE_PARSERS (core/registry.py), eine kleine Registry
    statt der vormaligen hartkodierten `if lang in {"cobol", "copybook"}`-
    Weiche. Das hier haengt einen Fake-"Sprache"-Eintrag in genau diese
    Registry ein und beweist so, dass der Dispatch-Mechanismus selbst fuer
    JEDE registrierte Sprache greift -- ohne eine zweite echte Sprache
    vorzutaeuschen oder zu bauen (siehe docs/ADDING_A_LANGUAGE.md;
    O-077 entschied bewusst gegen eine neue `parser/languages/`-Vorrats-
    Abstraktion entscheidet). Der Fake-Eintrag hat bewusst keinen
    prepare_source-Hook (O-079)."""
    connector = GitConnector(source_id=-1)
    calls = []

    def fake_parse(text_, path, *, prepared_source=None, **kwargs):
        calls.append((text_, path, prepared_source))
        return ParseResult(
            program_name="FAKE",
            path=path,
            source_format="free",
            chunks=[Chunk(content=text_, start_line=1, end_line=1, meta={"fake": True})],
        )

    doc = {
        "title": "fake.xyz",
        "content": "fake source",
        "url": "fake://fake.xyz",
        "source_type": "Git",
        "storage_key": "fake.xyz",
        "extra_meta": {"language": "fakelang"},
    }

    with (
        patch("connectors.git.STRUCTURE_PARSERS", {"fakelang": ParserEntry(parse=fake_parse)}),
        patch("connectors.git.get_embeddings_batch", AsyncMock(return_value=[[0.1] * 1024])),
        patch("connectors.git.asyncio.to_thread", _run_to_thread_inline),
    ):
        _, chunks, parse_result = await connector._embed_document(doc, asyncio.Semaphore(1))

    # O-079: der Fake-Eintrag hat keinen prepare_source-Hook, also wird
    # None durchgereicht -- das beweist, dass der Hook wirklich optional ist.
    assert calls == [("fake source", "fake.xyz", None)]
    assert parse_result is not None and parse_result.program_name == "FAKE"
    assert len(chunks) == 1
    assert chunks[0]["content"] == "fake source"
    assert chunks[0]["start_line"] == 1
    assert chunks[0]["end_line"] == 1
    assert chunks[0]["meta"] == {"fake": True}


def test_reuse_unchanged_embeddings_only_returns_new_content_for_embedding():
    """O-122: Reparse aktualisiert Struktur, aber nicht den Vektor eines
    unveränderten indexierbaren Textes."""
    chunks = [
        {"content": "unchanged source"},
        {"content": "new source"},
    ]
    old_chunks = [SimpleNamespace(content="unchanged source", embedding=[0.25] * 1024)]

    to_embed = _reuse_unchanged_embeddings(chunks, old_chunks)

    assert chunks[0]["embedding"] == [0.25] * 1024
    assert to_embed == [{"content": "new source"}]


def test_reuse_unchanged_embeddings_rejects_unknown_or_old_model_vectors():
    old_chunks = [
        SimpleNamespace(content="legacy vector", embedding=[0.25] * 1024, embedding_model=None),
        SimpleNamespace(content="old model vector", embedding=[0.5] * 1024, embedding_model="old"),
    ]
    chunks = [{"content": "legacy vector"}, {"content": "old model vector"}]

    to_embed = _reuse_unchanged_embeddings(chunks, old_chunks, "new")

    assert to_embed == chunks
    assert all("embedding" not in chunk for chunk in chunks)


@pytest.mark.anyio
async def test_git_connector_falls_back_to_generic_chunking_for_unregistered_languages():
    """Gegenstück zum Test oben: eine Sprache ohne Registry-Eintrag (z. B.
    "text") nimmt weiterhin den generischen CodeParser-Pfad, nicht den
    Struktur-Parser-Zweig."""
    connector = GitConnector(source_id=-1)
    doc = {
        "title": "readme.md",
        "content": "# hi\n",
        "url": "fake://readme.md",
        "source_type": "Git",
        "storage_key": "readme.md",
        "extra_meta": {"language": "text"},
    }

    with patch("connectors.git.get_embeddings_batch", AsyncMock(return_value=[[0.1] * 1024])):
        _, chunks, parse_result = await connector._embed_document(doc, asyncio.Semaphore(1))

    assert parse_result is None
    assert chunks and chunks[0]["content"].strip() == "# hi"
