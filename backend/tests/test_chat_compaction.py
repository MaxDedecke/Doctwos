"""Compacting des Gesprächsverlaufs und seitenweises Laden langer Chats."""

import uuid
from types import SimpleNamespace

import pytest

from codena_models.database import ChatMessage, ChatSession, User
from services import chat_compaction
from services.chat_compaction import prepare_conversation
from services.chat_sessions import page_messages

_PROFILE = SimpleNamespace(
    id=1,
    provider="ollama",
    protocol="ollama",
    llm_model="m",
    llm_api_key=None,
    llm_base_url=None,
    llm_path=None,
    llm_context_length=2048,
    capabilities_json=None,
)


@pytest.fixture
def long_session(db_session):
    """Sitzung mit sechs Runden zu je rund 1.000 Zeichen; das Verlaufsbudget (4.000 Zeichen) reicht nicht."""
    user = User(
        username=f"compaction-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Compaction",
        password_hash="x",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    session = ChatSession(title="Lang", owner_id=user.id)
    db_session.add(session)
    db_session.commit()
    messages = []
    for index in range(6):
        for role in ("user", "assistant"):
            message = ChatMessage(
                session_id=session.id, role=role, content=f"{role} {index} " + "x" * 990
            )
            db_session.add(message)
            db_session.commit()
            messages.append(message)
    yield session, messages
    db_session.query(ChatSession).filter(ChatSession.id == session.id).delete()
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


@pytest.fixture
def summaries(monkeypatch):
    calls = []

    async def summarize(_profile, previous, messages):
        calls.append((previous, [message.id for message in messages]))
        return f"Zusammenfassung {len(calls)}"

    monkeypatch.setattr(chat_compaction, "summarize", summarize)
    return calls


def _ask(db_session, session, text="Neue Frage") -> ChatMessage:
    message = ChatMessage(session_id=session.id, role="user", content=text)
    db_session.add(message)
    db_session.commit()
    return message


async def _prepare(db_session, session, user_message, profile=_PROFILE):
    events = [
        event async for event in prepare_conversation(db_session, session, user_message, profile)
    ]
    return events[:-1], events[-1]["conversation"]


@pytest.mark.asyncio
async def test_a_conversation_within_budget_goes_verbatim(db_session, long_session, summaries):
    session, messages = long_session
    question = messages[4]  # zwei Runden davor passen ins Budget

    steps, conversation = await _prepare(db_session, session, question)

    assert steps == [] and summaries == []
    assert [m.id for m in conversation.history] == [m.id for m in messages[:4]]
    assert conversation.system_block() == ""


@pytest.mark.asyncio
async def test_an_overflowing_history_is_folded_into_a_stored_summary(
    db_session, long_session, summaries
):
    session, messages = long_session
    question = _ask(db_session, session)

    steps, conversation = await _prepare(db_session, session, question)

    assert [step["status"] for step in steps] == ["running", "ok"]
    assert steps[-1] == {"type": "history_compacted", "messages": 10, "status": "ok"}
    assert summaries == [(None, [m.id for m in messages[:10]])]
    assert [m.id for m in conversation.history] == [m.id for m in messages[10:]]
    assert "Zusammenfassung 1" in conversation.system_block()
    assert conversation.steps == [steps[-1]]
    db_session.refresh(session)
    assert session.context_summary == "Zusammenfassung 1"
    assert session.context_summary_upto_id == messages[9].id


@pytest.mark.asyncio
async def test_the_next_turn_reuses_the_summary_without_another_model_call(
    db_session, long_session, summaries
):
    session, messages = long_session
    await _prepare(db_session, session, _ask(db_session, session))

    steps, conversation = await _prepare(
        db_session, session, _ask(db_session, session, "Noch eine")
    )

    assert len(summaries) == 1 and steps == []
    assert conversation.summary == "Zusammenfassung 1"
    assert conversation.history[0].id == messages[10].id


@pytest.mark.asyncio
async def test_retrying_an_old_answer_does_not_use_a_summary_of_later_messages(
    db_session, long_session, summaries
):
    session, messages = long_session
    await _prepare(db_session, session, _ask(db_session, session))
    old_question = messages[8]  # liegt vor dem Ende der gespeicherten Zusammenfassung

    steps, conversation = await _prepare(db_session, session, old_question)

    assert summaries[-1] == (None, [m.id for m in messages[:6]])
    assert all(m.id < old_question.id for m in conversation.history)
    assert conversation.summary == "Zusammenfassung 2"
    db_session.refresh(session)
    assert session.context_summary == "Zusammenfassung 1"


@pytest.mark.asyncio
async def test_a_failed_summary_keeps_the_turn_going_with_recent_messages(
    db_session, long_session, monkeypatch
):
    session, messages = long_session

    async def broken(*_args):
        raise RuntimeError("Modell weg")

    monkeypatch.setattr(chat_compaction, "summarize", broken)

    steps, conversation = await _prepare(db_session, session, _ask(db_session, session))

    assert steps[-1]["status"] == "failed"
    assert conversation.summary is None
    assert [m.id for m in conversation.history] == [m.id for m in messages[10:]]
    db_session.refresh(session)
    assert session.context_summary is None


def test_messages_are_paged_newest_first_without_splitting_a_turn(db_session, long_session):
    session, messages = long_session

    first, more = page_messages(db_session, session.id, limit=5, before_id=None)
    assert more is True
    assert [m["id"] for m in first] == [m.id for m in messages[8:]]

    second, more = page_messages(db_session, session.id, limit=5, before_id=first[0]["id"])
    assert more is True and second[0]["role"] == "user"
    third, more = page_messages(db_session, session.id, limit=5, before_id=second[0]["id"])
    assert more is False
    assert [m["id"] for m in third + second + first] == [m.id for m in messages]


def test_the_page_endpoint_checks_access(client, long_session):
    session, _ = long_session

    response = client.get(f"/chat/sessions/{session.id}/messages/page?limit=4")

    assert response.status_code == 404
