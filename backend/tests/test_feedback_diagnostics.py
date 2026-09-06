"""Regression tests for explicit, local O-088 feedback diagnostic capture."""

from datetime import datetime, timedelta, timezone

import pytest

from conftest import TEST_USERNAME
from models.database import (
    ChatFeedbackDiagnosticCase,
    ChatFeedbackDiagnosticSettings,
    ChatMessage,
    ChatSession,
    User,
)


@pytest.fixture(autouse=True)
def isolated_diagnostic_settings(db_session):
    """The integration suite shares a DB; never leak an opt-in between tests."""
    settings = db_session.query(ChatFeedbackDiagnosticSettings).first()
    original = None
    if settings:
        original = (
            settings.collection_enabled,
            settings.support_export_enabled,
            settings.retention_days,
            settings.updated_by_user_id,
        )
    else:
        settings = ChatFeedbackDiagnosticSettings()
        db_session.add(settings)
    settings.collection_enabled = False
    settings.support_export_enabled = False
    settings.retention_days = 90
    db_session.commit()

    yield

    if original is None:
        db_session.delete(settings)
    else:
        (
            settings.collection_enabled,
            settings.support_export_enabled,
            settings.retention_days,
            settings.updated_by_user_id,
        ) = original
    db_session.commit()


def test_admin_opt_in_captures_minimal_case_and_gates_export(client, db_session):
    user = db_session.query(User).filter(User.username == TEST_USERNAME).first()
    session = ChatSession(title="diagnostic case", owner_id=user.id)
    db_session.add(session)
    db_session.commit()
    question = ChatMessage(session_id=session.id, role="user", content="Was macht dieses Programm?")
    answer = ChatMessage(
        session_id=session.id,
        role="assistant",
        content="Eine falsche Erklärung.",
        sources_json=[{"file": "program.cbl", "chunk_id": 12}],
        metadata_json={"model": "local-model", "provider": "ollama", "agent_steps": [{"secret": "nope"}]},
    )
    db_session.add_all([question, answer])
    db_session.commit()

    assert client.get("/feedback-diagnostics/settings").json()["collection_enabled"] is False
    enabled = client.patch(
        "/feedback-diagnostics/settings",
        json={"collection_enabled": True, "support_export_enabled": True, "retention_days": 30},
    )
    assert enabled.status_code == 200

    assert client.patch(f"/chat/messages/{answer.id}/feedback", json={"feedback": "down"}).status_code == 200
    cases = client.get("/feedback-diagnostics/cases")
    assert cases.status_code == 200
    entry = next(item for item in cases.json()["entries"] if item["message_id"] == answer.id)
    assert entry["question"] == "Was macht dieses Programm?"
    assert entry["answer"] == "Eine falsche Erklärung."
    assert entry["model"] == "local-model"
    assert "agent_steps" not in entry

    exported = client.get("/feedback-diagnostics/export")
    assert exported.status_code == 200
    assert exported.json()["generated_locally"] is True

    # A withdrawn downvote must not remain in support diagnostics.
    assert client.patch(f"/chat/messages/{answer.id}/feedback", json={"feedback": None}).status_code == 200
    assert not db_session.query(ChatFeedbackDiagnosticCase).filter(
        ChatFeedbackDiagnosticCase.chat_message_id == answer.id
    ).first()

    db_session.delete(session)
    db_session.commit()


def test_feedback_diagnostic_export_needs_explicit_admin_opt_in(client):
    response = client.get("/feedback-diagnostics/export")
    assert response.status_code == 403


def test_diagnostic_settings_validate_retention_and_disable_export(client):
    assert client.patch(
        "/feedback-diagnostics/settings",
        json={"collection_enabled": True, "support_export_enabled": True, "retention_days": 0},
    ).status_code == 400
    assert client.patch(
        "/feedback-diagnostics/settings",
        json={"collection_enabled": True, "support_export_enabled": True, "retention_days": 366},
    ).status_code == 400

    response = client.patch(
        "/feedback-diagnostics/settings",
        json={"collection_enabled": False, "support_export_enabled": True, "retention_days": 90},
    )
    assert response.status_code == 200
    assert response.json()["support_export_enabled"] is False


def test_diagnostic_endpoints_are_admin_only(member_client):
    for method, path, needs_body in (
        (member_client.get, "/feedback-diagnostics/settings", False),
        (member_client.get, "/feedback-diagnostics/cases", False),
        (member_client.get, "/feedback-diagnostics/export", False),
        (member_client.delete, "/feedback-diagnostics/cases", False),
        (member_client.patch, "/feedback-diagnostics/settings", True),
    ):
        kwargs = {"json": {"collection_enabled": False, "retention_days": 90}} if needs_body else {}
        assert method(path, **kwargs).status_code == 403


def test_expired_diagnostic_cases_are_purged(client, db_session):
    user = db_session.query(User).filter(User.username == TEST_USERNAME).first()
    session = ChatSession(title="expired diagnostic", owner_id=user.id)
    message = ChatMessage(session=session, role="assistant", content="alte Antwort")
    db_session.add_all([session, message])
    db_session.commit()
    case = ChatFeedbackDiagnosticCase(
        chat_message_id=message.id,
        answer="alte Antwort",
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db_session.add(case)
    db_session.commit()
    assert client.patch(
        "/feedback-diagnostics/settings",
        json={"collection_enabled": True, "support_export_enabled": False, "retention_days": 1},
    ).status_code == 200

    assert client.get("/feedback-diagnostics/cases").json()["entries"] == []

    db_session.delete(session)
    db_session.commit()


def test_admin_can_delete_all_diagnostic_cases(client, db_session):
    user = db_session.query(User).filter(User.username == TEST_USERNAME).first()
    session = ChatSession(title="delete diagnostics", owner_id=user.id)
    message = ChatMessage(session=session, role="assistant", content="zu löschen")
    db_session.add_all([session, message])
    db_session.commit()
    db_session.add(ChatFeedbackDiagnosticCase(chat_message_id=message.id, answer="zu löschen"))
    db_session.commit()

    response = client.delete("/feedback-diagnostics/cases")
    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert db_session.query(ChatFeedbackDiagnosticCase).count() == 0

    db_session.delete(session)
    db_session.commit()
