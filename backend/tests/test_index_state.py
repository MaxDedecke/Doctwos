"""Indexstand einer Wissensquelle: Erkennung, Hinweis in Antworten, Job-Center."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import mcp_server
from api import jobs as jobs_api
from doctus_models.database import ChatSession, KnowledgeSource
from services import index_state

INDEXED = datetime(2026, 10, 1, 8, 30, tzinfo=timezone.utc)


def _source(status, indexed_at=INDEXED, commit="0123456789abcdef"):
    return SimpleNamespace(
        id=7,
        name="carddemo",
        sync_status=status,
        indexed_at=indexed_at,
        sync_cursor={"last_commit": commit} if commit else None,
    )


@pytest.mark.parametrize(
    ("status", "indexed_at", "running", "expected"),
    [
        ("completed", INDEXED, None, "current"),
        ("pending", INDEXED, None, "current"),  # erneut eingereiht, Daten unverändert
        ("pending", None, None, "not_indexed"),
        ("syncing", INDEXED, True, "updating"),
        ("syncing", INDEXED, None, "updating"),  # Redis unbekannt: nicht als Absturz werten
        ("syncing", INDEXED, False, "interrupted"),
        ("error", INDEXED, None, "incomplete"),
        ("cancelled", INDEXED, None, "incomplete"),
        ("error", None, None, "not_indexed"),
    ],
)
def test_index_state_distinguishes_running_crashed_and_failed_runs(
    status, indexed_at, running, expected
):
    assert index_state.index_state(_source(status, indexed_at), running) == expected


def test_answer_notice_names_the_last_complete_revision():
    entry = index_state.describe(_source("syncing"), "interrupted")
    notice = index_state.answer_notice([entry])
    assert "„carddemo“ Einlesen wurde abgebrochen" in notice
    assert "Commit 0123456789" in notice and "2026-10-01 08:30 UTC" in notice
    assert "unterschiedlichen Ständen" in notice
    assert index_state.answer_notice([]) == ""


@pytest.fixture
def project_source(db_session, test_project, test_team):
    source = KnowledgeSource(
        name="Indexstand-Quelle",
        type="Git",
        project_id=test_project,
        team_id=test_team,
        sync_status="completed",
        indexed_at=INDEXED,
        sync_cursor={"last_commit": "feedfacecafe"},
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    yield source
    db_session.rollback()
    db_session.query(ChatSession).filter(ChatSession.project_id == test_project).delete()
    db_session.delete(source)
    db_session.commit()


def test_evidence_pack_carries_the_index_status_only_when_the_index_is_mixed(
    db_session, test_project, project_source, monkeypatch
):
    assert "index_status" not in mcp_server._with_index_status(db_session, test_project, {})

    project_source.sync_status = "syncing"
    db_session.commit()
    monkeypatch.setattr(index_state, "sync_running", lambda _source_id: False)

    status = mcp_server._with_index_status(db_session, test_project, {})["index_status"]
    assert [(s["source"], s["state"]) for s in status["sources"]] == [
        ("Indexstand-Quelle", "interrupted")
    ]
    assert status["sources"][0]["indexed_revision"] == "feedfacecafe"


def test_a_crashed_sync_is_shown_as_failed_and_can_be_restarted(
    client, db_session, project_source, monkeypatch
):
    project_source.sync_status = "syncing"
    db_session.commit()

    monkeypatch.setattr(jobs_api, "sync_running", lambda _source_id: True)
    job = next(
        j for j in client.get("/jobs").json()["jobs"] if j["key"] == f"source:{project_source.id}"
    )
    assert (job["status"], job["can_resume"]) == ("running", False)

    monkeypatch.setattr(jobs_api, "sync_running", lambda _source_id: False)
    job = next(
        j for j in client.get("/jobs").json()["jobs"] if j["key"] == f"source:{project_source.id}"
    )
    assert (job["status"], job["can_resume"]) == ("failed", True)
    assert "Einlesen abgebrochen" in job["error_message"]

    sent = []
    monkeypatch.setattr(jobs_api.celery_app, "send_task", lambda *a, **k: sent.append(a))
    assert client.post(f"/jobs/source/{project_source.id}/start").status_code == 200
    assert sent == [("process_knowledge_source",)]


@pytest.mark.parametrize("agent", [False, True])
def test_the_streamed_answer_is_the_final_answer_including_index_notice(
    client, db_session, test_project, project_source, monkeypatch, agent
):
    """Was nach der Modellantwort angehängt wird (Indexhinweis, Quellen-Rückfall des
    Agenten), muss schon im gestreamten ``answer`` stehen, nicht erst nach Neuladen."""
    project_source.sync_status = "error"
    db_session.commit()

    async def embed(*args, **kwargs):
        return [0.01] * 1024

    async def stream(**kwargs):
        if agent:
            yield {
                "type": "tool_result",
                "name": "view_repo_file",
                "id": "call-1",
                "result": json.dumps(
                    {"file_path": "src/PAY.cbl", "start_line": 10, "end_line": 12}
                ),
            }
        yield {"type": "answer", "content": "Die Zahlung wird geprüft."}

    monkeypatch.setattr("services.chat_service.embed_text", embed)
    monkeypatch.setattr("services.chat_turn.agent_profile_supports_tools", lambda _: agent)
    monkeypatch.setattr("services.chat_turn.stream_agent_events", stream)
    monkeypatch.setattr("services.chat_turn.stream_standard_rag_events", stream)

    response = client.post(
        "/chat",
        json={"message": "Wie wird die Zahlung geprüft?", "project_id": test_project},
    )
    assert response.status_code == 200
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    types = [event["type"] for event in events]
    assert types.count("answer") == 1
    assert types.index("answer") < types.index("sources")

    streamed = next(event["content"] for event in events if event["type"] == "answer")
    assert (
        "Hinweis zum Indexstand" in streamed and "letztes Einlesen endete mit Fehlern" in streamed
    )
    if agent:
        assert "`src/PAY.cbl:10`" in streamed

    session_uuid = next(e["session_uuid"] for e in events if e["type"] == "session")
    history = client.get(f"/chat/sessions/by-uuid/{session_uuid}/messages").json()
    stored = next(row for row in history if row["role"] == "assistant")
    assert stored["content"] == streamed
    assert stored["metadata_json"]["index_status"][0]["state"] == "incomplete"
