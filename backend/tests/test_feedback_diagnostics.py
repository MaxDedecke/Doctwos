"""Regression tests for explicit, local O-088 feedback diagnostic capture."""

from conftest import TEST_USERNAME
from models.database import (
    ChatFeedbackDiagnosticCase,
    ChatFeedbackDiagnosticSettings,
    ChatMessage,
    ChatSession,
    User,
)


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

    db_session.query(ChatFeedbackDiagnosticSettings).delete()
    db_session.delete(session)
    db_session.commit()


def test_feedback_diagnostic_export_needs_explicit_admin_opt_in(client):
    response = client.get("/feedback-diagnostics/export")
    assert response.status_code == 403
