"""Insight citations survive retrieval, SSE delivery and stored chat history."""

import json
from datetime import datetime, timezone

import pytest

from doctus_models.database import ChatMessage, ChatSession, Insight, User


@pytest.mark.parametrize("agent", [False, True])
def test_chat_exposes_only_cited_insights_in_sse_and_history(
    client, db_session, test_project, monkeypatch, agent
):
    user = db_session.query(User).filter_by(username="test-fixture-user").one()
    insights = [
        Insight(
            project_id=test_project,
            title=f"Zahlungsregel {index}",
            content="Zahlung wird vor dem Buchen geprüft.",
            origin_kind="code",
            evidence_json=[{"file": "PAY.cbl", "start_line": 15}],
            status="verified",
            created_by_id=user.id,
            verified_by_id=user.id,
            verified_at=datetime.now(timezone.utc),
        )
        for index in range(2)
    ]
    db_session.add_all(insights)
    db_session.commit()
    insight_id = insights[0].id

    async def embed(*args, **kwargs):
        return [0.01] * 1024

    async def stream(**kwargs):
        assert f"[Insight:{insight_id}]" in kwargs["prompt"]
        yield {
            "type": "answer",
            "content": f"Die Zahlung wird vor dem Buchen geprüft [Insight:{insight_id}].",
        }

    monkeypatch.setattr("services.chat_service.embed_text", embed)
    monkeypatch.setattr("services.chat_turn.agent_profile_supports_tools", lambda _: agent)
    monkeypatch.setattr("services.chat_turn.stream_agent_events", stream)
    monkeypatch.setattr("services.chat_turn.stream_standard_rag_events", stream)
    session_id = None
    try:
        response = client.post(
            "/chat",
            json={
                "message": "Was besagt die Zahlungsregel?",
                "project_id": test_project,
                "mode": "evidence",
            },
        )
        assert response.status_code == 200
        events = [
            json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
        ]
        session_event = next(event for event in events if event["type"] == "session")
        session_id = session_event["session_id"]
        sources = next(event["sources"] for event in events if event["type"] == "sources")
        assert len(sources) == 1
        assert sources[0]["kind"] == "insight"
        assert sources[0]["insight_id"] == insight_id
        assert sources[0]["title"] == insights[0].title
        assert sources[0]["evidence"] == [{"file": "PAY.cbl", "start_line": 15}]
        stored = (
            db_session.query(ChatMessage).filter_by(session_id=session_id, role="assistant").one()
        )
        assert stored.sources_json == sources
        history = client.get(f"/chat/sessions/by-uuid/{session_event['session_uuid']}/messages")
        assert history.status_code == 200
        assert (
            next(row for row in history.json() if row["role"] == "assistant")["sources_json"]
            == sources
        )
    finally:
        if session_id is not None:
            db_session.query(ChatSession).filter_by(id=session_id).delete()
        for insight in insights:
            db_session.delete(insight)
        db_session.commit()
