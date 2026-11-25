"""Zuverlässigkeit des Chats: Stream-Abschluss, Wiederholung, Denkfilter, Werkzeugstatus, Kontextkürzung."""

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

from api import chat as chat_api
from codena_models.database import ChatLinkFeedbackSignal, ChatMessage, ChatSession, User
from services.agent_tool_results import tool_result_failed
from services.chat_sessions import begin_turn, persist_assistant_message, serialize_messages
from services.think_filter import ThinkFilter, strip_thinking
from test_agent_model_robustness import _ollama_line, _run, _serve


def _live_text(pieces: list[str]) -> str:
    """Was die Live-Anzeige nach allen Stücken zeigt: ein Rücksetzen verwirft das bisher Gezeigte."""
    think_filter, shown = ThinkFilter(), ""
    for piece in pieces:
        visible = think_filter.feed(piece)
        if think_filter.take_reset():
            shown = ""
        shown += visible
    return shown + think_filter.flush()


@pytest.mark.parametrize(
    "pieces",
    [
        ["überlegen, ", "weiter</th", "ink>\n\nAntwort"],
        ["erst</think>dann", " doch</think>Antwort"],
        ["<think>a</think>Eins ", "<think>b</think>Zwei"],
        ["</think>Antwort"],
        ["Kein Denken"],
    ],
)
def test_live_display_ends_with_the_same_text_as_the_final_cleanup(pieces):
    assert _live_text(pieces).lstrip() == strip_thinking("".join(pieces))


def test_reset_is_only_reported_when_text_was_already_shown():
    think_filter = ThinkFilter()
    assert think_filter.feed("</think>Antwort") == "Antwort"
    assert think_filter.take_reset() is False

    think_filter = ThinkFilter()
    think_filter.feed("überlegen")
    think_filter.feed("</think>Antwort")
    assert think_filter.take_reset() is True
    assert think_filter.take_reset() is False


@pytest.mark.parametrize(
    "result, metadata, failed",
    [
        ('{"error": "Datei nicht gefunden"}', {}, True),
        ('{"error": null, "files": []}', {}, False),
        ("Fehler: Werkzeug 'x' ist nicht registriert.", {}, True),
        ("Ergebnis", {"mcp_status": "error"}, True),
        ("Ergebnis", {"mcp_status": "success"}, False),
        ('{"files": ["a.cbl"]', {}, False),
        ('[{"error": "kein Objekt"}]', {}, False),
    ],
)
def test_tool_failures_are_recognized_in_every_reporting_form(result, metadata, failed):
    assert tool_result_failed(result, metadata) is failed


class _FailingMcpClient:
    name = "fake-mcp"

    async def list_tools(self):
        return [{"name": "lookup", "description": "", "inputSchema": {"type": "object"}}]

    async def call_tool(self, _name, _arguments):
        return {"isError": True, "content": [{"type": "text", "text": "Server nicht erreichbar"}]}


@pytest.mark.asyncio
async def test_tool_results_carry_status_and_duration_and_the_answer_is_no_thought(monkeypatch):
    _serve(
        monkeypatch,
        [[_ollama_line(text="Ich schaue nach.", call="lookup")], [_ollama_line(text="Antwort")]],
    )

    events = await _run("ollama", mcp_clients=[_FailingMcpClient()])

    result = next(event for event in events if event["type"] == "tool_result")
    assert result["status"] == "error"
    assert isinstance(result["duration_ms"], int) and result["duration_ms"] >= 0
    answer = events[-1]
    assert answer["type"] == "answer" and answer["content"] == "Antwort"
    thoughts = [step["content"] for step in answer["agent_steps"] if step["type"] == "thought"]
    assert thoughts == ["Ich schaue nach."]


@pytest.mark.asyncio
async def test_trimming_the_conversation_is_reported_as_its_own_step(monkeypatch):
    _serve(monkeypatch, [[_ollama_line(text="Antwort")]])
    history = [
        {"role": role, "content": "Langer früherer Beitrag. " * 400}
        for role in ("user", "assistant") * 2
    ]

    events = await _run("ollama", chat_history=history, context_length=2048)

    trimmed = [event for event in events if event["type"] == "context_trimmed"]
    assert trimmed and "history" in trimmed[0]["parts"]
    assert trimmed[0] in events[-1]["agent_steps"]


@pytest.mark.asyncio
async def test_disconnect_while_the_model_runs_cancels_the_turn():
    started, cleaned, cancelled = asyncio.Event(), asyncio.Event(), []

    async def turn():
        yield {"type": "session"}
        try:
            started.set()
            await asyncio.sleep(3600)
            yield {"type": "answer"}
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        finally:
            cleaned.set()

    stream = chat_api._sse(turn())
    assert json.loads((await stream.__anext__())[len("data: ") :]) == {"type": "session"}
    consumer = asyncio.ensure_future(stream.__anext__())
    await started.wait()
    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer

    await asyncio.wait_for(cleaned.wait(), 1)
    assert cancelled == [True]


@pytest.mark.asyncio
async def test_disconnect_between_events_closes_the_turn():
    cleaned = asyncio.Event()

    async def turn():
        try:
            yield {"type": "session"}
            yield {"type": "answer"}
        finally:
            cleaned.set()

    stream = chat_api._sse(turn())
    await stream.__anext__()
    await stream.aclose()

    await asyncio.wait_for(cleaned.wait(), 1)


@pytest.fixture
def conversation(db_session):
    """Sitzung mit drei Runden: Frage/Antwort 0, 1 und 2."""
    user = User(
        username=f"chat-reliability-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        name="Chat Reliability",
        password_hash="x",
        role="user",
    )
    db_session.add(user)
    db_session.commit()
    session = ChatSession(title="Wiederholung", owner_id=user.id)
    db_session.add(session)
    db_session.commit()
    messages = []
    for index in range(3):
        for role, text in (("user", f"Frage {index}"), ("assistant", f"Antwort {index}")):
            message = ChatMessage(session_id=session.id, role=role, content=text)
            db_session.add(message)
            db_session.commit()
            messages.append(message)
    yield session, messages, user
    db_session.query(ChatSession).filter(ChatSession.id == session.id).delete()
    db_session.query(User).filter(User.id == user.id).delete()
    db_session.commit()


def _retry_request(message: ChatMessage) -> SimpleNamespace:
    return SimpleNamespace(retry_of_message_id=message.id, message="", metadata={}, mode="evidence")


def test_retrying_an_older_answer_sees_only_the_conversation_before_it(db_session, conversation):
    session, messages, _ = conversation

    turn = begin_turn(db_session, session, _retry_request(messages[3]))

    assert turn.user_message.id == messages[2].id
    assert turn.replaced_answer.id == messages[3].id
    assert [message.content for message in turn.history] == ["Frage 0", "Antwort 0"]


def test_a_new_question_sees_the_whole_recent_conversation(db_session, conversation):
    session, _, _ = conversation
    request = SimpleNamespace(
        retry_of_message_id=None, message="Frage 3", metadata={}, mode="evidence"
    )

    turn = begin_turn(db_session, session, request)

    assert [message.content for message in turn.history] == [
        f"{kind} {index}" for index in range(3) for kind in ("Frage", "Antwort")
    ]


def test_a_regenerated_answer_keeps_its_place_and_drops_feedback_on_the_old_one(
    db_session, conversation
):
    session, messages, user = conversation
    old = messages[3]
    old.feedback = "down"
    db_session.add(
        ChatLinkFeedbackSignal(
            chat_message_id=old.id,
            chat_session_id=session.id,
            user_id=user.id,
            link_type="knowledge",
            link_id=1,
        )
    )
    db_session.commit()

    saved = persist_assistant_message(
        db=db_session,
        session_id=session.id,
        answer="Neue Antwort 1",
        sources=[],
        model="m",
        provider="ollama",
        agent_steps=[],
        previous_message=old,
    )

    assert saved.id == old.id
    assert saved.feedback is None
    assert (
        db_session.query(ChatLinkFeedbackSignal)
        .filter(ChatLinkFeedbackSignal.chat_message_id == old.id)
        .count()
        == 0
    )
    assert [message["content"] for message in serialize_messages(session.id, db_session)] == [
        "Frage 0",
        "Antwort 0",
        "Frage 1",
        "Neue Antwort 1",
        "Frage 2",
        "Antwort 2",
    ]


def _edit_request(message: ChatMessage, text: str) -> SimpleNamespace:
    return SimpleNamespace(
        edit_of_message_id=message.id,
        retry_of_message_id=None,
        message=text,
        metadata={},
        mode="evidence",
    )


def test_editing_the_last_question_replaces_its_text_and_then_its_answer(db_session, conversation):
    session, messages, _ = conversation

    turn = begin_turn(db_session, session, _edit_request(messages[4], "Frage 2, genauer"))

    assert turn.user_message.id == messages[4].id
    assert turn.user_message.content == "Frage 2, genauer"
    assert turn.user_message.metadata_json["edited"] is True
    assert turn.replaced_answer.id == messages[5].id
    assert [m.content for m in turn.history][-1] == "Antwort 1"


def test_only_the_last_question_can_be_edited(db_session, conversation):
    from services.chat_errors import ChatInvalid

    session, messages, _ = conversation

    with pytest.raises(ChatInvalid):
        begin_turn(db_session, session, _edit_request(messages[2], "neu"))
