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
from unittest.mock import patch, AsyncMock, MagicMock

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
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"
        ),
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
    db_session.add(
        DocumentChunk(
            project_id=test_source.project_id,
            source_id=test_source.id,
            file_path="Runbook",
            content="alte Fassung",
            start_line=1,
            end_line=1,
            embedding=[0.0] * 1024,
        )
    )
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


@pytest.mark.anyio
async def test_confluence_connector_attaches_line_sections(db_session, test_source):
    """O-082: fetch_documents() liefert pro Zeile die zuletzt gültige
    Überschrift mit, damit _process_document() daraus meta["section"] pro
    Chunk ableiten kann."""
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    html = "<h1>Setup</h1><p>Schritt 1.</p><h2>Betrieb</h2><p>Schritt 2.</p>"
    page_response = {"results": [_page(html=html)], "_links": {}}

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
    lines = docs[0]["content"].split("\n")
    line_sections = docs[0]["line_sections"]
    assert len(lines) == len(line_sections)
    assert line_sections[lines.index("Schritt 1.")] == "Setup"
    assert line_sections[lines.index("Schritt 2.")] == "Betrieb"


@pytest.mark.anyio
async def test_confluence_connector_process_document_stores_section_metadata(
    db_session, test_source
):
    """O-082 Ende-zu-Ende: _process_document() (gemeinsamer Pfad für alle
    generischen Connectoren, base.py) reichert metadata_json jedes Chunks um
    die Section an, in der er in der Confluence-Seite stand."""
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    # Bewusst nur EINE Section über den ganzen Inhalt (kein Abschnittswechsel)
    # -- dieser Test prüft ausschließlich die metadata_json-Anreicherung,
    # nicht das section-bewusste Schneiden selbst (siehe O-083-Test unten).
    doc = {
        "title": "Runbook",
        "content": "Setup\n\nSchritt 1.\n\nSchritt 2.",
        "url": "https://example.atlassian.net/spaces/DOCS/pages/123/Runbook",
        "source_type": "Confluence",
        "storage_key": "Runbook",
        "extra_meta": {"page_id": "123"},
        "line_sections": ["Setup", "Setup", "Setup", "Setup", "Setup"],
    }

    with patch("connectors.base.get_embedding", AsyncMock(return_value=[0.0] * 1024)):
        await connector._process_document(doc)
    connector.db.commit()

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == "Runbook")
        .order_by(DocumentChunk.start_line)
        .all()
    )
    assert len(chunks) == 1
    assert chunks[0].metadata_json["section"] == "Setup"
    # Nicht-Section-Felder (url/title/source_type/page_id) bleiben unverändert.
    assert chunks[0].metadata_json["title"] == "Runbook"
    assert chunks[0].metadata_json["page_id"] == "123"


@pytest.mark.anyio
async def test_confluence_connector_process_document_without_sections_unaffected(
    db_session, test_source
):
    """Regression: eine Seite ohne jede Überschrift (line_sections nur None)
    darf weiterhin keinen "section"-Schlüssel in metadata_json bekommen --
    sonst würde ein leerer Wert die spätere Chat-Zitat-Anzeige verwirren."""
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    doc = {
        "title": "Notizen",
        "content": "Ein Absatz ohne jede Überschrift.",
        "url": None,
        "source_type": "Confluence",
        "storage_key": "Notizen",
        "extra_meta": {"page_id": "456"},
        "line_sections": [None],
    }

    with patch("connectors.base.get_embedding", AsyncMock(return_value=[0.0] * 1024)):
        await connector._process_document(doc)
    connector.db.commit()

    chunk = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == "Notizen")
        .one()
    )
    assert "section" not in chunk.metadata_json


@pytest.mark.anyio
async def test_confluence_connector_process_document_cuts_at_section_boundary(
    db_session, test_source
):
    """O-083: zwei kurze Sections, die zusammen locker unter CHUNK_SIZE
    passen, landen trotzdem als zwei getrennte Chunks -- die Section-Grenze
    schneidet, bevor die Zeichenzahl-Schwelle das täte."""
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    doc = {
        "title": "Runbook",
        "content": "Setup\n\nKurzer Schritt.\n\nBetrieb\n\nNoch kürzer.",
        "url": None,
        "source_type": "Confluence",
        "storage_key": "Runbook",
        "extra_meta": {"page_id": "789"},
        "line_sections": ["Setup", "Setup", "Setup", "Setup", "Betrieb", "Betrieb", "Betrieb"],
    }

    with patch("connectors.base.get_embedding", AsyncMock(return_value=[0.0] * 1024)):
        await connector._process_document(doc)
    connector.db.commit()

    chunks = (
        db_session.query(DocumentChunk)
        .filter(DocumentChunk.source_id == test_source.id, DocumentChunk.file_path == "Runbook")
        .order_by(DocumentChunk.start_line)
        .all()
    )
    assert len(chunks) == 2
    assert chunks[0].metadata_json["section"] == "Setup"
    assert "Betrieb" not in chunks[0].content
    assert chunks[1].metadata_json["section"] == "Betrieb"
    assert "Setup" not in chunks[1].content
