"""Quellen-Ausfälle (Fehlerart, wachsende Pausen, Löschschutz) und der Modellwechsel eines Projekts."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import text

import worker
from connectors import errors
from connectors.gitlab_issues import GitLabIssuesConnector
from db import SessionLocal
from codena_models.database import DocumentChunk, EmbeddingMigration, KnowledgeSource
from tasks import embedding_migration as job


def _http_error(code):
    request = httpx.Request("GET", "https://wiki.intern/rest/api/content")
    return httpx.HTTPStatusError(
        "x", request=request, response=httpx.Response(code, request=request)
    )


@pytest.mark.parametrize(
    "exc, kind",
    [
        (_http_error(401), errors.AUTH),
        (_http_error(403), errors.AUTH),
        (_http_error(404), errors.NOT_FOUND),
        (_http_error(503), errors.NETWORK),
        (httpx.ConnectError("refused"), errors.NETWORK),
        (ValueError("Select explicit GitLab project IDs"), errors.CONFIG),
        (RuntimeError("fatal: Authentication failed for 'https://git.intern/x.git'"), errors.AUTH),
        (RuntimeError("Could not resolve host: git.intern"), errors.NETWORK),
    ],
)
def test_failures_are_classified_so_the_admin_knows_what_to_do(exc, kind):
    assert errors.classify_exception(exc) == kind


def test_outcome_counts_failures_in_a_row_and_resets_on_success():
    source = SimpleNamespace(
        sync_status="error", last_error="401 Unauthorized", error_kind=None, failure_count=1
    )
    errors.record_outcome(source)
    assert (source.failure_count, source.error_kind) == (2, errors.AUTH)
    source.sync_status = "completed"
    errors.record_outcome(source)
    assert (source.failure_count, source.error_kind) == (0, None)
    assert source.last_attempt_at is not None


def _src(failures, kind, attempted_minutes_ago, synced_minutes_ago=600):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        failure_count=failures,
        error_kind=kind,
        last_attempt_at=now - timedelta(minutes=attempted_minutes_ago),
        last_synced_at=now - timedelta(minutes=synced_minutes_ago),
    )


def test_auto_sync_backs_off_after_failures_and_pauses_on_rejected_credentials():
    now = datetime.now(timezone.utc)
    # Erfolgreich: fällig nach dem Intervall
    assert worker._auto_sync_due(_src(0, None, 0, synced_minutes_ago=60), 60, now)
    # Dritter Fehlschlag wegen Netzwerk: 4 · 60 min Abstand
    assert not worker._auto_sync_due(_src(3, "network", 200), 60, now)
    assert worker._auto_sync_due(_src(3, "network", 240), 60, now)
    # Höchstens ein Tag Abstand
    assert worker._auto_sync_due(_src(12, "network", 24 * 60), 60, now)
    # Abgelehnte Zugangsdaten: nach drei Fehlschlägen keine automatischen Versuche mehr
    assert worker._auto_sync_due(_src(2, "auth", 120), 60, now)
    assert not worker._auto_sync_due(_src(3, "auth", 10 * 24 * 60), 60, now)


# ── Datenbank: Löschschutz und Modellwechsel ──────────────────────────────────


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def project(db):
    team_id = db.execute(
        text("INSERT INTO teams (name, created_at) VALUES ('health-team', now()) RETURNING id")
    ).scalar_one()
    project_id = db.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES ('health', :t, now()) RETURNING id"
        ),
        {"t": team_id},
    ).scalar_one()
    db.commit()
    yield SimpleNamespace(id=project_id, team_id=team_id)
    db.rollback()
    db.execute(text("DELETE FROM embedding_migrations WHERE project_id = :p"), {"p": project_id})
    db.execute(
        text(
            "DELETE FROM document_chunks WHERE project_id = :p OR source_id IN "
            "(SELECT id FROM knowledge_sources WHERE project_id = :p)"
        ),
        {"p": project_id},
    )
    db.execute(text("DELETE FROM knowledge_sources WHERE project_id = :p"), {"p": project_id})
    db.execute(text("DELETE FROM projects WHERE id = :p"), {"p": project_id})
    db.execute(text("DELETE FROM teams WHERE id = :t"), {"t": team_id})
    db.commit()


def _source(db, project, **extra):
    source = KnowledgeSource(
        name="Issues",
        type="GitLabIssues",
        project_id=project.id,
        team_id=project.team_id,
        sync_status="completed",
        embedding_model="old-model",
        **extra,
    )
    db.add(source)
    db.commit()
    return source


def _chunks(db, source, count, model="old-model", dim=4):
    for i in range(count):
        db.add(
            DocumentChunk(
                project_id=source.project_id,
                source_id=source.id,
                file_path=f"7/issues/{i}",
                content=f"Issue {i}",
                start_line=1,
                end_line=1,
                embedding=[float(i + 1)] * dim,
                embedding_model=model,
            )
        )
    db.commit()


def test_gitlab_issues_keep_the_index_when_the_api_suddenly_lists_almost_nothing(db, project):
    source = _source(db, project)
    _chunks(db, source, 40)
    connector = GitLabIssuesConnector(source.id)

    removed = connector._remove_orphans({"7/issues/0"})

    db.expire_all()
    assert removed == 0
    assert db.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).count() == 40
    refreshed = db.get(KnowledgeSource, source.id)
    assert (refreshed.sync_status, refreshed.error_kind) == ("error", "source_content")
    assert "nichts gelöscht" in refreshed.sync_log


def test_gitlab_issues_still_remove_the_last_deleted_issue(db, project):
    source = _source(db, project)
    _chunks(db, source, 1)

    assert GitLabIssuesConnector(source.id)._remove_orphans(set()) == 1


@pytest.fixture
def new_model(monkeypatch):
    """Zielmodell mit 6 Dimensionen statt 4; jeder Vektor kennt seinen Text."""

    async def embed(texts, model=None, retries=3):
        width = 6 if model == "new-model" else 4
        return [[float(len(t))] * width for t in texts]

    monkeypatch.setattr(job, "get_embeddings_batch", embed)
    monkeypatch.setattr(job, "_ensure_index", lambda _db, _dim: None)


def _migration(db, project):
    migration = EmbeddingMigration(
        project_id=project.id,
        target_model="new-model",
        previous_model="old-model",
        status="embedding",
        total=3,
    )
    db.add(migration)
    db.commit()
    return migration


def _models(db, project):
    db.expire_all()
    return sorted(
        (c.embedding_model, c.embedding_dimension, c.embedding_next_model)
        for c in db.query(DocumentChunk).filter(DocumentChunk.project_id == project.id)
    )


@pytest.mark.anyio
async def test_model_change_builds_in_the_shadow_switches_at_once_and_rolls_back(
    db, project, new_model
):
    source = _source(db, project)
    _chunks(db, source, 3)
    migration = _migration(db, project)

    await job.run(migration.id)
    db.expire_all()
    assert db.get(EmbeddingMigration, migration.id).status == "ready"
    # Die Suche sieht weiter nur den alten Raum.
    assert _models(db, project) == [("old-model", 4, "new-model")] * 3

    # Ein Sync legt zwischen Lauf und Umschalten einen neuen Abschnitt an; das Umschalten zieht ihn nach.
    _chunks(db, source, 1)
    await job.switch(migration.id)
    db.expire_all()
    assert db.get(EmbeddingMigration, migration.id).status == "switched"
    assert _models(db, project) == [("new-model", 6, "old-model")] * 4
    assert db.get(KnowledgeSource, source.id).embedding_model == "new-model"

    await job.rollback(migration.id)
    db.expire_all()
    assert db.get(EmbeddingMigration, migration.id).status == "rolled_back"
    assert _models(db, project) == [("old-model", 4, "new-model")] * 4
    assert db.get(KnowledgeSource, source.id).embedding_model == "old-model"

    job.cleanup(migration.id)
    db.expire_all()
    assert _models(db, project) == [("old-model", 4, None)] * 4
    assert db.get(EmbeddingMigration, migration.id).status == "cleaned"


@pytest.mark.anyio
async def test_switch_waits_while_a_source_of_the_project_syncs(
    db, project, new_model, monkeypatch
):
    source = _source(db, project)
    _chunks(db, source, 2)
    migration = _migration(db, project)
    await job.run(migration.id)

    class Busy:
        def __init__(self, _sid):
            pass

        def acquire(self):
            return False

    monkeypatch.setattr(job, "SyncLock", Busy)
    await job.switch(migration.id)

    db.expire_all()
    stored = db.get(EmbeddingMigration, migration.id)
    assert stored.status == "ready" and "synchronisiert gerade" in stored.error
    assert _models(db, project) == [("old-model", 4, "new-model")] * 2


@pytest.mark.anyio
async def test_a_failed_run_resumes_where_it_stopped(db, project, monkeypatch):
    source = _source(db, project)
    _chunks(db, source, 3)
    migration = _migration(db, project)
    monkeypatch.setattr(job, "BATCH", 1)
    calls = {"n": 0}

    async def flaky(texts, model=None, retries=3):
        calls["n"] += 1
        if calls["n"] == 2:
            raise httpx.ConnectError("embedding service down")
        return [[1.0] * 6 for _ in texts]

    monkeypatch.setattr(job, "get_embeddings_batch", flaky)
    await job.run(migration.id)
    db.expire_all()
    stored = db.get(EmbeddingMigration, migration.id)
    assert stored.status == "failed" and "embedding service down" in stored.error
    assert stored.done == 1

    await job.run(migration.id)
    db.expire_all()
    stored = db.get(EmbeddingMigration, migration.id)
    assert (stored.status, stored.done) == ("ready", 3)
