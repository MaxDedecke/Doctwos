"""Sitzungen umbenennen, anheften, im Titel suchen und exportieren; Anhänge an Fragen."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from conftest import TEST_USERNAME
from doctus_models.database import ChatMessage, ChatSession, User
from services import chat_attachments
from services.chat_errors import ChatInvalid
from services.chat_sessions import begin_turn


@pytest.fixture
def own_sessions(client, db_session):
    user = db_session.query(User).filter(User.username == TEST_USERNAME).one()
    created = []
    for title in ("Zinsberechnung COBIL00C", "Login-Ablauf", "Zins 100% prüfen"):
        session = ChatSession(title=title, owner_id=user.id)
        db_session.add(session)
        db_session.commit()
        created.append(session)
    yield created, user
    for session in created:
        db_session.query(ChatSession).filter(ChatSession.id == session.id).delete()
    db_session.commit()


def test_sessions_can_be_renamed_pinned_and_found_by_title(client, own_sessions):
    sessions, _ = own_sessions

    renamed = client.patch(
        f"/chat/sessions/{sessions[1].id}", json={"title": "Anmeldung", "is_pinned": True}
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Anmeldung" and renamed.json()["is_pinned"] is True

    found = client.get("/chat/sessions/page", params={"general": True, "q": "zins"}).json()[
        "sessions"
    ]
    assert {s["id"] for s in found} >= {sessions[0].id, sessions[2].id}
    assert sessions[1].id not in {s["id"] for s in found}
    literal = client.get("/chat/sessions/page", params={"general": True, "q": "100%"}).json()[
        "sessions"
    ]
    assert [s["id"] for s in literal] == [sessions[2].id]
    pinned = client.get("/chat/sessions/page", params={"general": True, "pinned": True}).json()[
        "sessions"
    ]
    assert [s["id"] for s in pinned] == [sessions[1].id]
    assert client.patch(f"/chat/sessions/{sessions[1].id}", json={"title": "  "}).status_code == 400


def test_a_session_exports_as_markdown_with_sources(client, db_session, own_sessions):
    sessions, _ = own_sessions
    db_session.add_all(
        [
            ChatMessage(
                session_id=sessions[0].id,
                role="user",
                content="Wie wird der Zins berechnet?",
                metadata_json={"attachments": [{"name": "log.txt", "chars": 10}]},
            ),
            ChatMessage(
                session_id=sessions[0].id,
                role="assistant",
                content="Über `COBIL00C.cbl:120`.",
                sources_json=[{"file": "app/cbl/COBIL00C.cbl", "lines": [120, 125]}],
                metadata_json={"model": "qwen3:8b", "chat_mode": "evidence"},
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/chat/sessions/{sessions[0].id}/export")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    text = response.text
    assert text.startswith("# Zinsberechnung COBIL00C")
    assert "## Frage\n\nWie wird der Zins berechnet?" in text
    assert "Anhänge: `log.txt`" in text
    assert "## Antwort (qwen3:8b · evidence)" in text
    assert "- `app/cbl/COBIL00C.cbl:120-125`" in text


def test_attachments_are_stored_encrypted_and_only_named_in_metadata(db_session, own_sessions):
    sessions, _ = own_sessions
    request = SimpleNamespace(
        retry_of_message_id=None,
        edit_of_message_id=None,
        message="Was bedeutet dieser Abbruch?",
        metadata={},
        mode="evidence",
        attachments=[{"name": "job.log", "content": "IEF450I ABEND=S0C7"}],
    )

    turn = begin_turn(db_session, sessions[0], request)

    assert chat_attachments.load(turn.user_message.attachments) == request.attachments
    assert turn.user_message.metadata_json["attachments"] == [{"name": "job.log", "chars": 18}]
    raw = db_session.execute(
        text("SELECT attachments FROM chat_messages WHERE id = :id"), {"id": turn.user_message.id}
    ).scalar()
    assert raw and "S0C7" not in raw


def test_attachments_are_bounded_and_marked_as_untrusted():
    block = chat_attachments.prompt_block([{"name": 'a"b.log', "content": "x" * 50_000}], 8192)
    assert block.count("<untrusted_attachment") == 1 and "name='a\"b.log'" in block
    assert "Anhang gekürzt" in block and len(block) < 9_000
    with pytest.raises(ChatInvalid):
        chat_attachments.validate([{"name": f"{i}.txt", "content": "x"} for i in range(6)])
    assert json.loads(chat_attachments.dump([{"name": "n", "content": "c"}])) == [
        {"name": "n", "content": "c"}
    ]
