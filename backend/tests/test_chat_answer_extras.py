"""Antwortversionen beim Wiederholen, Gründe beim Daumen runter und Folgevorschläge."""

import uuid

import pytest

from doctus_models.database import ChatMessage, ChatSession, User
from services import chat_followups
from services.chat_feedback import set_message_feedback
from services.chat_followups import follow_up_suggestions, parse_suggestions
from services.chat_sessions import MAX_ANSWER_VERSIONS, persist_assistant_message
from services.chat_errors import ChatInvalid


@pytest.fixture
def answered(db_session):
    user = User(
        username=f"extras-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Extras",
        password_hash="x",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    session = ChatSession(title="Extras", owner_id=user.id)
    db_session.add(session)
    db_session.commit()
    question = ChatMessage(session_id=session.id, role="user", content="Wer ruft COSGN00C auf?")
    db_session.add(question)
    db_session.commit()
    answer = ChatMessage(
        session_id=session.id,
        role="assistant",
        content="Fassung 0",
        sources_json=[{"file": "a.cbl"}],
        metadata_json={"model": "m"},
    )
    db_session.add(answer)
    db_session.commit()
    yield session, answer, user
    db_session.query(ChatSession).filter(ChatSession.id == session.id).delete()
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


def _regenerate(db_session, session, answer, text):
    return persist_assistant_message(
        db=db_session,
        session_id=session.id,
        answer=text,
        sources=[],
        model="m",
        provider="ollama",
        agent_steps=[],
        previous_message=answer,
    )


def test_regenerating_keeps_earlier_versions_oldest_first_and_bounded(db_session, answered):
    session, answer, _ = answered
    for index in range(1, MAX_ANSWER_VERSIONS + 3):
        answer = _regenerate(db_session, session, answer, f"Fassung {index}")

    versions = answer.metadata_json["versions"]
    assert answer.content == f"Fassung {MAX_ANSWER_VERSIONS + 2}"
    assert len(versions) == MAX_ANSWER_VERSIONS
    assert [v["content"] for v in versions][-1] == f"Fassung {MAX_ANSWER_VERSIONS + 1}"
    assert versions[0]["content"] == "Fassung 2"


def test_a_downvote_reason_is_stored_and_cleared_with_the_downvote(db_session, answered):
    _, answer, user = answered

    set_message_feedback(
        db_session, answer, "down", user, reason="wrong_source", comment=" Zeile falsch "
    )
    assert answer.metadata_json["feedback_reason"] == {
        "reason": "wrong_source",
        "comment": "Zeile falsch",
    }
    set_message_feedback(db_session, answer, "up", user)
    assert "feedback_reason" not in answer.metadata_json
    with pytest.raises(ChatInvalid):
        set_message_feedback(db_session, answer, "down", user, reason="erfunden")


def test_suggestions_are_cleaned_up():
    text = "1. Wer ruft COSGN00C auf?\n- Welche Felder liest es?\n\nWer ruft COSGN00C auf?\nok\n• Gibt es Tests?\nNoch eine?"
    assert parse_suggestions(text) == [
        "Wer ruft COSGN00C auf?",
        "Welche Felder liest es?",
        "Gibt es Tests?",
    ]


@pytest.mark.asyncio
async def test_suggestions_are_generated_once_and_stored(db_session, answered, monkeypatch):
    _, answer, _ = answered
    calls = []

    async def stream(**kwargs):
        calls.append(kwargs["prompt"])
        yield {
            "type": "answer",
            "content": "Welche Programme rufen es auf?\nWas steht in COCOM01Y?",
        }

    monkeypatch.setattr(chat_followups, "stream_standard_rag_events", stream)
    profile = type(
        "P",
        (),
        dict(
            provider="ollama",
            llm_model="m",
            llm_api_key=None,
            llm_base_url=None,
            protocol="ollama",
            llm_path=None,
            llm_context_length=8192,
            capabilities_json=None,
        ),
    )()

    first = await follow_up_suggestions(db_session, answer, profile)
    second = await follow_up_suggestions(db_session, answer, profile)

    assert first == second == ["Welche Programme rufen es auf?", "Was steht in COCOM01Y?"]
    assert len(calls) == 1 and "Wer ruft COSGN00C auf?" in calls[0]
