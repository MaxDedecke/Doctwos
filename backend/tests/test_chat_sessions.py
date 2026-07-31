import json

import pytest

from models.database import ChatSession, User

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

    def _make_session(owner_id, title="test session") -> ChatSession:
        session = ChatSession(title=title, owner_id=owner_id)
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


def test_shared_session_remains_readable_via_uuid_regardless_of_owner(client, make_session, other_user):
    """The sharing feature: a session not in your own list must still be fully
    reachable (viewable and resumable) via its UUID link."""
    other_session = make_session(other_user.id, title="shared with me")

    resp = client.get(f"/chat/sessions/by-uuid/{other_session.uuid}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "shared with me"

    messages_resp = client.get(f"/chat/sessions/by-uuid/{other_session.uuid}/messages")
    assert messages_resp.status_code == 200
