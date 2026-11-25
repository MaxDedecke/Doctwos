"""Quellenzustand für Admins, Schutz des Vektorraums beim Profilwechsel und die API des Modellwechsels je Projekt."""

from types import SimpleNamespace

import pytest

from api import knowledge_sources as sources_api
from codena_models.database import (
    DocumentChunk,
    EmbeddingMigration,
    EmbeddingProfile,
    KnowledgeSource,
    User,
)
from services import job_control, source_health
from core.auth_dependency import SESSION_COOKIE_NAME, create_session_cookie_value
from tests.conftest import TEST_MEMBER_USERNAME


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def send_task(name, args=None, **_kwargs):
        calls.append((name, args))
        return SimpleNamespace(id=f"task-{len(calls)}")

    monkeypatch.setattr(job_control.celery_app, "send_task", send_task)
    return calls


@pytest.fixture
def profiles(db_session):
    old = EmbeddingProfile(name="Alt", model="old-embed", base_url="http://e1", dimension=4)
    new = EmbeddingProfile(name="Neu", model="new-embed", base_url="http://e2", dimension=6)
    db_session.add_all([old, new])
    db_session.commit()
    yield SimpleNamespace(old=old, new=new)
    db_session.query(EmbeddingMigration).filter(
        EmbeddingMigration.profile_id.in_([old.id, new.id])
    ).delete(synchronize_session=False)
    db_session.query(EmbeddingProfile).filter(EmbeddingProfile.id.in_([old.id, new.id])).delete(
        synchronize_session=False
    )
    db_session.commit()


@pytest.fixture
def indexed(db_session, test_project, test_team):
    source = KnowledgeSource(
        name="Wiki",
        type="Confluence",
        project_id=test_project,
        team_id=test_team,
        sync_status="completed",
        embedding_model="old-embed",
    )
    db_session.add(source)
    db_session.commit()
    for i in range(3):
        db_session.add(
            DocumentChunk(
                project_id=test_project,
                source_id=source.id,
                file_path=f"page-{i}",
                content="x",
                embedding=[1.0, 0.0, 0.0, 0.0],
                embedding_model="old-embed",
            )
        )
    db_session.commit()
    yield source
    db_session.query(EmbeddingMigration).filter(
        EmbeddingMigration.project_id == test_project
    ).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.query(KnowledgeSource).filter(KnowledgeSource.project_id == test_project).delete()
    db_session.commit()


def test_source_carries_a_hint_and_the_pause_state(client, indexed, db_session):
    indexed.sync_status = "error"
    indexed.error_kind = "auth"
    indexed.failure_count = 3
    indexed.last_error = "401 Unauthorized"
    db_session.commit()

    item = next(s for s in client.get("/knowledge-sources").json() if s["id"] == indexed.id)

    assert item["error_kind"] == "auth" and "Token oder Passwort" in item["error_hint"]
    assert item["auto_sync_paused"] is True and item["failure_count"] == 3


def test_a_manual_sync_lifts_the_pause(indexed, db_session, sent):
    indexed.failure_count = 4
    db_session.commit()
    job_control.send_tracked_task(db_session, indexed, "process_knowledge_source", [indexed.id])
    assert indexed.failure_count == 0
    assert not source_health.auto_sync_paused(indexed)


def test_health_reports_failing_sources_by_number_only(unauthenticated_client, indexed, db_session):
    indexed.sync_status = "error"
    db_session.commit()

    sources = unauthenticated_client.get("/health").json()["sources"]

    assert sources["failing"] >= 1
    assert set(sources) == {"total", "failing", "paused", "overdue"}


def test_model_of_a_used_profile_cannot_be_changed_in_place(client, profiles, indexed):
    response = client.patch(f"/embedding-profiles/{profiles.old.id}", json={"model": "other"})
    assert response.status_code == 409
    assert "neues Embedding-Profil" in response.json()["detail"]
    # Die Adresse darf sich ändern, der Vektorraum bleibt derselbe.
    assert (
        client.patch(
            f"/embedding-profiles/{profiles.old.id}", json={"base_url": "http://e9"}
        ).status_code
        == 200
    )


def test_activating_another_profile_keeps_existing_projects_and_says_so(
    client, profiles, indexed, db_session, test_project
):
    response = client.post(f"/embedding-profiles/{profiles.new.id}/activate")
    assert response.status_code == 200
    assert response.json()["projects_on_other_models"] >= 1
    # Eine neue Quelle im bestehenden Projekt bleibt im Raum des Projekts.
    assert sources_api._source_embedding_model(db_session, test_project, None) == "old-embed"
    assert sources_api._source_embedding_model(db_session, None, None) == "new-embed"


def test_model_change_api_starts_once_and_follows_the_state_machine(
    client, profiles, indexed, test_project, db_session, sent
):
    base = f"/projects/{test_project}/embedding-migration"
    state = client.get(base).json()
    assert state["models"] == {"old-embed": 3} and state["migration"] is None

    started = client.post(base, json={"profile_id": profiles.new.id})
    assert started.status_code == 202
    migration = started.json()
    assert (migration["target_model"], migration["previous_model"], migration["total"]) == (
        "new-embed",
        "old-embed",
        3,
    )
    assert sent[-1] == ("embedding_migration", [migration["id"], "run"])
    assert client.post(base, json={"profile_id": profiles.new.id}).status_code == 409

    # Umschalten erst, wenn alle Schattenvektoren stehen.
    assert client.post(f"{base}/{migration['id']}/switch").status_code == 409
    db_session.query(EmbeddingMigration).filter(EmbeddingMigration.id == migration["id"]).update(
        {"status": "ready"}
    )
    db_session.commit()
    assert client.post(f"{base}/{migration['id']}/switch").status_code == 202
    assert sent[-1] == ("embedding_migration", [migration["id"], "switch"])


def test_model_change_is_refused_for_the_model_the_project_already_uses(
    client, profiles, indexed, test_project
):
    response = client.post(
        f"/projects/{test_project}/embedding-migration", json={"profile_id": profiles.old.id}
    )
    assert response.status_code == 409


def test_members_may_not_start_a_model_change(
    member_client, profiles, indexed, test_project, db_session
):
    # test_project hängt am Admin-Client derselben TestClient-Instanz; die Sitzung ausdrücklich auf das Mitglied setzen.
    member = db_session.query(User).filter(User.username == TEST_MEMBER_USERNAME).one()
    member_client.cookies.set(SESSION_COOKIE_NAME, create_session_cookie_value(member.id))
    base = f"/projects/{test_project}/embedding-migration"
    assert member_client.post(base, json={"profile_id": profiles.new.id}).status_code == 403
