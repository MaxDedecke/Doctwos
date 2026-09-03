import json

import pytest

from models.database import ChatMessage, ChatSession, KnowledgeSource, User

OTHER_USERNAME = "test-fixture-sub-other"
OTHER_USER_EMAIL = "fixture-user-other@example.com"


@pytest.fixture
def other_user(db_session):
    """A second user, distinct from the `client` fixture's logged-in user — never logged in itself, just an owner to test isolation against."""
    user = User(username=OTHER_USERNAME, email=OTHER_USER_EMAIL, name="Other Fixture User",
                password_hash="x", role="user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


@pytest.fixture
def make_session(db_session):
    created_ids = []

    def _make_session(owner_id, title="test session", is_public=False) -> ChatSession:
        session = ChatSession(title=title, owner_id=owner_id, is_public=is_public)
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        created_ids.append(session.id)
        return session

    yield _make_session

    for session_id in created_ids:
        db_session.query(ChatSession).filter(ChatSession.id == session_id).delete()
    db_session.commit()


def _first_sse_event(body: str) -> dict:
    line = next(l for l in body.splitlines() if l.startswith("data: "))
    return json.loads(line[len("data: "):])


def test_new_chat_session_is_owned_by_the_creating_user(client, db_session):
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 200

    event = _first_sse_event(resp.text)
    assert event["type"] == "session"
    session = db_session.query(ChatSession).filter(ChatSession.id == event["session_id"]).first()
    assert session is not None
    assert session.owner_id is not None
    db_session.query(ChatSession).filter(ChatSession.id == session.id).delete()
    db_session.commit()


def test_chat_sessions_list_only_shows_own_sessions(client, make_session, other_user):
    other_session = make_session(other_user.id, title="someone else's chat")

    resp = client.get("/chat/sessions")
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert other_session.id not in ids


def test_owner_can_delete_their_own_session(client, db_session):
    resp = client.post("/chat", json={"message": "hi"})
    session_id = _first_sse_event(resp.text)["session_id"]

    del_resp = client.delete(f"/chat/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert db_session.query(ChatSession).filter(ChatSession.id == session_id).first() is None


def test_deleting_someone_elses_session_is_forbidden(client, make_session, other_user, db_session):
    other_session = make_session(other_user.id)

    resp = client.delete(f"/chat/sessions/{other_session.id}")
    assert resp.status_code == 403
    assert db_session.query(ChatSession).filter(ChatSession.id == other_session.id).first() is not None


def test_publicly_shared_session_is_readable_via_uuid_by_another_user(client, make_session, other_user):
    """The sharing feature: once explicitly shared (is_public), a session not in
    your own list must still be fully reachable (viewable and resumable) via its
    UUID link."""
    other_session = make_session(other_user.id, title="shared with me", is_public=True)

    resp = client.get(f"/chat/sessions/by-uuid/{other_session.uuid}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "shared with me"

    messages_resp = client.get(f"/chat/sessions/by-uuid/{other_session.uuid}/messages")
    assert messages_resp.status_code == 200


def test_never_shared_session_is_not_readable_via_uuid_by_another_user(client, make_session, other_user):
    """O-032: a session that was never explicitly shared (is_public stays False by
    default) must not be readable via its UUID, even though the UUID itself is
    hard to guess."""
    other_session = make_session(other_user.id, title="private chat", is_public=False)

    resp = client.get(f"/chat/sessions/by-uuid/{other_session.uuid}")
    assert resp.status_code == 404

    messages_resp = client.get(f"/chat/sessions/by-uuid/{other_session.uuid}/messages")
    assert messages_resp.status_code == 404


def test_by_uuid_routes_require_authentication(unauthenticated_client, make_session, other_user):
    other_session = make_session(other_user.id, is_public=True)

    resp = unauthenticated_client.get(f"/chat/sessions/by-uuid/{other_session.uuid}")
    assert resp.status_code == 401


def test_get_messages_by_id_forbidden_for_non_owner_private_session(client, make_session, other_user):
    """O-032: /chat/sessions/{id}/messages used sequential, guessable IDs with no
    auth/ownership check at all — must now require owner or is_public."""
    other_session = make_session(other_user.id, is_public=False)

    resp = client.get(f"/chat/sessions/{other_session.id}/messages")
    assert resp.status_code == 404


def test_get_messages_by_id_allowed_for_public_session(client, make_session, other_user):
    other_session = make_session(other_user.id, is_public=True)

    resp = client.get(f"/chat/sessions/{other_session.id}/messages")
    assert resp.status_code == 200


def test_owner_can_share_own_session(client, db_session):
    resp = client.post("/chat", json={"message": "hi"})
    session_id = _first_sse_event(resp.text)["session_id"]

    share_resp = client.post(f"/chat/sessions/{session_id}/share")
    assert share_resp.status_code == 200
    assert share_resp.json()["is_public"] is True

    session = db_session.query(ChatSession).filter(ChatSession.id == session_id).first()
    assert session.is_public is True

    db_session.query(ChatSession).filter(ChatSession.id == session_id).delete()
    db_session.commit()


def test_sharing_someone_elses_session_is_forbidden(client, make_session, other_user, db_session):
    other_session = make_session(other_user.id, is_public=False)

    resp = client.post(f"/chat/sessions/{other_session.id}/share")
    assert resp.status_code == 403
    db_session.refresh(other_session)
    assert other_session.is_public is False


def test_snapshot_update_forbidden_for_non_owner_private_session(client, make_session, other_user):
    other_session = make_session(other_user.id, is_public=False)

    resp = client.patch(f"/chat/sessions/{other_session.id}/snapshot", json={"snapshot": {}})
    assert resp.status_code == 404


def test_snapshot_update_allowed_for_public_session(client, make_session, other_user, db_session):
    other_session = make_session(other_user.id, is_public=True)

    resp = client.patch(f"/chat/sessions/{other_session.id}/snapshot", json={"snapshot": {"a": 1}})
    assert resp.status_code == 200
    db_session.refresh(other_session)
    assert other_session.snapshot_json == {"a": 1}


def test_feedback_update_forbidden_for_non_owner_private_session(client, make_session, other_user, db_session):
    other_session = make_session(other_user.id, is_public=False)
    msg = ChatMessage(session_id=other_session.id, role="assistant", content="hi there")
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)

    resp = client.patch(f"/chat/messages/{msg.id}/feedback", json={"feedback": "up"})
    assert resp.status_code == 404

    db_session.query(ChatMessage).filter(ChatMessage.id == msg.id).delete()
    db_session.commit()


def test_continuing_someone_elses_private_session_via_chat_is_forbidden(client, make_session, other_user):
    other_session = make_session(other_user.id, is_public=False)

    resp = client.post("/chat", json={"message": "hi", "session_id": other_session.id})
    assert resp.status_code == 404


# ── O-038: Sitzung ohne Chat-Nachricht anlegen ────────────────────────────────
# Gegenstück zur impliziten Session-Erzeugung in POST /chat -- deckt den Fall
# ab, dass ein Befund nur über mehrere Views (z.B. Graph + Code) entsteht, ohne
# dass der Chat je benutzt wurde.

def test_create_session_without_message_is_owned_and_untitled_from_no_message(client, db_session):
    resp = client.post("/chat/sessions", json={"title": "Brandschutz-Befund"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Brandschutz-Befund"
    assert body["uuid"] is not None

    session = db_session.query(ChatSession).filter(ChatSession.id == body["id"]).first()
    assert session is not None
    assert session.owner_id is not None
    assert session.snapshot_json is None

    messages = client.get(f"/chat/sessions/{body['id']}/messages")
    assert messages.status_code == 200
    assert messages.json() == []

    db_session.query(ChatSession).filter(ChatSession.id == body["id"]).delete()
    db_session.commit()


def test_create_session_without_message_stores_the_given_snapshot(client, db_session):
    snapshot = {"panelConfigs": ["graph", "code"], "activeRightTab": "graph"}
    resp = client.post("/chat/sessions", json={"title": "Graph-Befund", "snapshot": snapshot})
    assert resp.status_code == 200
    session_id = resp.json()["id"]

    session = db_session.query(ChatSession).filter(ChatSession.id == session_id).first()
    assert session.snapshot_json == snapshot

    db_session.query(ChatSession).filter(ChatSession.id == session_id).delete()
    db_session.commit()


def test_create_session_without_message_appears_in_own_session_list(client, db_session):
    resp = client.post("/chat/sessions", json={"title": "Sichtbarer Befund"})
    session_id = resp.json()["id"]

    listing = client.get("/chat/sessions")
    assert any(s["id"] == session_id for s in listing.json())

    db_session.query(ChatSession).filter(ChatSession.id == session_id).delete()
    db_session.commit()


def test_create_session_without_message_rejects_blank_title(client):
    resp = client.post("/chat/sessions", json={"title": "   "})
    assert resp.status_code == 400


def test_create_session_without_message_rejects_unknown_project(client):
    resp = client.post("/chat/sessions", json={"title": "x", "project_id": 999999})
    assert resp.status_code == 404


def test_create_session_without_message_rejects_unknown_source(client):
    resp = client.post("/chat/sessions", json={"title": "x", "source_id": 999999})
    assert resp.status_code == 404


def test_create_session_without_message_accepts_visible_project_and_source(client, db_session, test_project, test_team):
    source = KnowledgeSource(name="o38-source", type="Git", url="https://example.test/o38.git",
                             branch="main", project_id=test_project, team_id=test_team)
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    try:
        resp = client.post("/chat/sessions", json={
            "title": "Projekt-Befund", "project_id": test_project, "source_id": source.id,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == test_project
        assert body["source_id"] == source.id

        db_session.query(ChatSession).filter(ChatSession.id == body["id"]).delete()
        db_session.commit()
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_create_session_without_message_requires_authentication(unauthenticated_client):
    resp = unauthenticated_client.post("/chat/sessions", json={"title": "x"})
    assert resp.status_code == 401
