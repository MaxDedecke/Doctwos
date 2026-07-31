"""
Nachtest für den Confluence-Connector (AP-8, F-011) -- unverändert aus dem
Condo-Template übernommen, bisher aber ohne dedizierten Test. Verifiziert nach
den base.py-/registry.py-Anpassungen der letzten APs, dass Seiten-Fetch,
HTML-zu-Text-Umwandlung und Delta-Sync (unveränderte Seite überspringen)
weiterhin funktionieren.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from unittest.mock import patch, MagicMock

from db import SessionLocal
from models.database import KnowledgeSource, DocumentChunk
from connectors.confluence import ConfluenceConnector


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
        {"name": "confluence-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "confluence-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(
        name="Test Confluence",
        type="Confluence",
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


def _page(title="Runbook", when="2026-07-01T10:00:00.000Z", html="<p>Hallo <b>Welt</b></p>"):
    return {
        "id": "123",
        "title": title,
        "space": {"key": "DOCS"},
        "version": {"when": when},
        "body": {"view": {"value": html}},
        "_links": {"webui": "/spaces/DOCS/pages/123/" + title},
    }


@pytest.mark.anyio
async def test_confluence_connector_fetches_page_as_plaintext(db_session, test_source):
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    page_response = {"results": [_page()], "_links": {}}

    async def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "child/attachment" in url:
            resp.json = MagicMock(return_value={"results": []})
        else:
            resp.json = MagicMock(return_value=page_response)
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        docs = [doc async for doc in connector.fetch_documents()]

    assert len(docs) == 1
    assert docs[0]["title"] == "Runbook"
    assert "Hallo" in docs[0]["content"] and "Welt" in docs[0]["content"]
    assert docs[0]["source_type"] == "Confluence"
    assert docs[0]["storage_key"] == "Runbook"


@pytest.mark.anyio
async def test_confluence_connector_skips_unchanged_page_since_last_sync(db_session, test_source):
    test_source.last_synced_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    db_session.add(DocumentChunk(
        project_id=test_source.project_id,
        source_id=test_source.id,
        file_path="Runbook",
        content="alte Fassung",
        start_line=1,
        end_line=1,
        embedding=[0.0] * 1024,
    ))
    db_session.commit()
    db_session.refresh(test_source)

    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    # Seite wurde vor last_synced_at zuletzt geändert -> muss übersprungen werden.
    page_response = {"results": [_page(when="2026-07-01T10:00:00.000Z")], "_links": {}}

    async def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "child/attachment" in url:
            resp.json = MagicMock(return_value={"results": []})
        else:
            resp.json = MagicMock(return_value=page_response)
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        docs = [doc async for doc in connector.fetch_documents()]

    assert docs == []


@pytest.mark.anyio
async def test_confluence_connector_filters_by_space(db_session, test_source):
    test_source.spaces = ["DOCS"]
    db_session.commit()
    db_session.refresh(test_source)

    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    other_space_page = _page(title="Fremdraum-Seite")
    other_space_page["space"] = {"key": "OTHER"}
    page_response = {"results": [_page(), other_space_page], "_links": {}}

    async def mock_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "child/attachment" in url:
            resp.json = MagicMock(return_value={"results": []})
        else:
            resp.json = MagicMock(return_value=page_response)
        return resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        docs = [doc async for doc in connector.fetch_documents()]

    assert len(docs) == 1
    assert docs[0]["title"] == "Runbook"
