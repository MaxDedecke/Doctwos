"""Background embedding freshness, retries and model-context isolation."""

from uuid import uuid4
import pytest
from db import SessionLocal
from doctus_models.database import Team, User, Project, Insight, InsightEmbedding
from tasks import insight_embeddings as worker
from doctus_models.insight_workflow import content_hash


@pytest.fixture
def insight_fixture():
    with SessionLocal() as db:
        user = User(username="embed-" + uuid4().hex, role="superuser")
        team = Team(name="embed-" + uuid4().hex)
        db.add_all([user, team])
        db.flush()
        project = Project(name="embedding", team_id=team.id, creator_id=user.id)
        db.add(project)
        db.flush()
        from datetime import datetime, timezone

        insight = Insight(
            project_id=project.id,
            title="Zahlungsregel",
            content="Validate first.",
            origin_kind="code",
            status="verified",
            created_by_id=user.id,
            verified_by_id=user.id,
            verified_at=datetime.now(timezone.utc),
            evidence_json=[{"file": "A.java"}],
            version_bindings=[],
        )
        db.add(insight)
        db.commit()
        yield db, insight
        db.query(Insight).filter_by(project_id=project.id).delete(synchronize_session=False)
        db.delete(project)
        db.delete(team)
        db.delete(user)
        db.commit()


@pytest.fixture
def configured(monkeypatch):
    settings = {
        "provider": "ollama",
        "base_url": "http://fixture",
        "model": "fixture",
        "api_key": None,
        "path": None,
        "dimension": 1024,
        "context": 8100,
    }
    monkeypatch.setattr(worker, "_effective_embedding_settings", lambda: settings)
    return settings


@pytest.mark.asyncio
async def test_refresh_is_idempotent_and_reuses_unchanged_text(
    insight_fixture, configured, monkeypatch
):
    db, insight = insight_fixture
    calls = []

    async def embed(texts, *args):
        calls.append(texts)
        return [[1.0] + [0.0] * 1023]

    monkeypatch.setattr(worker, "_get_embeddings_sub_batch", embed)
    assert (await worker.refresh_insight_embeddings())["updated"] == 1
    db.expire_all()
    saved = db.get(InsightEmbedding, insight.id)
    assert saved.content_hash == content_hash(insight)
    insight.revision += 1
    db.commit()
    assert (await worker.refresh_insight_embeddings())["updated"] == 0
    assert len(calls) == 1
    configured["model"] = "different"
    assert (await worker.refresh_insight_embeddings())["updated"] == 1


@pytest.mark.asyncio
async def test_refresh_does_not_store_a_vector_after_concurrent_revision(
    insight_fixture, configured, monkeypatch
):
    db, insight = insight_fixture

    async def embed(*args):
        insight.content = "A different conclusion."
        db.commit()
        return [[1.0] + [0.0] * 1023]

    monkeypatch.setattr(worker, "_get_embeddings_sub_batch", embed)
    assert (await worker.refresh_insight_embeddings())["updated"] == 0
    assert db.get(InsightEmbedding, insight.id) is None


@pytest.mark.asyncio
async def test_refresh_failure_is_retryable_and_drafts_are_excluded(
    insight_fixture, configured, monkeypatch
):
    db, insight = insight_fixture

    async def failed(*args):
        raise OSError("offline")

    monkeypatch.setattr(worker, "_get_embeddings_sub_batch", failed)
    assert (await worker.refresh_insight_embeddings())["failed"] == 1
    assert db.get(InsightEmbedding, insight.id) is None
    insight.status = "draft"
    insight.verified_by_id = insight.verified_at = None
    db.commit()
    assert (await worker.refresh_insight_embeddings())["failed"] == 0
