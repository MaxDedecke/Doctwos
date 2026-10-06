"""
Nachtest für den Jira-Connector (AP-8, F-011) -- unverändert aus dem
Condo-Template übernommen, bisher aber ohne dedizierten Test. Verifiziert nach
den base.py-/registry.py-Anpassungen der letzten APs, dass Issue-Fetch (ADF ->
Plaintext, Kommentare) und der JQL-Aufbau für den Delta-Sync weiterhin
funktionieren.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from unittest.mock import patch, MagicMock

from db import SessionLocal
from models.database import KnowledgeSource, DocumentChunk
from connectors.jira import JiraConnector
from http_mocks import patch_http


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_source(db_session):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "jira-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"
        ),
        {"name": "jira-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(
        name="Test Jira",
        type="Jira",
        url="https://example.atlassian.net",
        username="bot@example.com",
        token="api-token-123",
        spaces=["ALL"],
        project_id=project_id,
        team_id=team_id,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    yield source

    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.delete(source)
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


@pytest.mark.anyio
async def test_jira_connector_fetches_issue_with_adf_description_and_comments(
    db_session, test_source
):
    connector = JiraConnector(test_source.id)
    connector.source = test_source

    search_response = {
        "total": 1,
        "issues": [
            {
                "key": "COBOL-42",
                "fields": {
                    "summary": "Rueckgabecode 8 nach COPY-Aenderung",
                    "description": {
                        "type": "doc",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Programm XAAOA bricht ab."}],
                            }
                        ],
                    },
                    "comment": {
                        "comments": [
                            {
                                "author": {"displayName": "M. Muster"},
                                "body": {
                                    "type": "doc",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [
                                                {"type": "text", "text": "Copybook geprueft."}
                                            ],
                                        }
                                    ],
                                },
                            }
                        ]
                    },
                },
            }
        ],
    }

    async def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=search_response)
        return resp

    with patch_http(mock_get):
        docs = [doc async for doc in connector.fetch_documents()]

    assert len(docs) == 1
    doc = docs[0]
    assert doc["title"] == "COBOL-42: Rueckgabecode 8 nach COPY-Aenderung"
    assert "Programm XAAOA bricht ab." in doc["content"]
    assert "Copybook geprueft." in doc["content"]
    assert doc["source_type"] == "Jira"
    assert doc["storage_key"] == "COBOL-42"


def test_jira_build_jql_combines_project_and_time_filter():
    connector = JiraConnector.__new__(JiraConnector)  # __init__ braucht DB/Source, hier nicht nötig
    connector.source = type(
        "FakeSource",
        (),
        {
            "last_synced_at": datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc),
        },
    )()

    jql = connector._build_jql(["COBOLPROJ"])

    assert "project=COBOLPROJ" in jql
    assert "updated >= '2026-07-20 09:30'" in jql


def test_jira_build_jql_falls_back_to_30_days_without_filters():
    connector = JiraConnector.__new__(JiraConnector)
    connector.source = type("FakeSource", (), {"last_synced_at": None})()

    assert connector._build_jql(["ALL"]) == "created >= -30d"


@pytest.mark.anyio
async def test_jira_server_uses_api_v2_without_backoff_and_reports_auth_errors(db_session, test_source, monkeypatch):
    import httpx

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    connector = JiraConnector(test_source.id)
    connector.source = test_source
    calls = []

    async def handler(url, **kwargs):
        calls.append(url)
        if "/rest/api/3/" in url:
            return httpx.Response(404, request=httpx.Request("GET", url))
        return httpx.Response(200, json={"total": 0, "issues": []}, request=httpx.Request("GET", url))

    with patch_http(handler):
        assert [doc async for doc in connector.fetch_documents()] == []
    assert sum(sleeps) < 1 and connector._search_path == "/rest/api/2/search"

    async def denied(url, **kwargs):
        return httpx.Response(401, request=httpx.Request("GET", url))

    connector2 = JiraConnector(test_source.id)
    connector2.source = test_source
    with patch_http(denied):
        with pytest.raises(RuntimeError, match="Anmeldung abgelehnt"):
            [doc async for doc in connector2.fetch_documents()]
