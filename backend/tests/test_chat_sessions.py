import json

import pytest

from models.database import ChatMessage, ChatSession, User

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
