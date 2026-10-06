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

    with patch_http(mock_get):
        docs = [doc async for doc in connector.fetch_documents()]

    assert len(docs) == 1
    assert docs[0]["title"] == "Runbook"
    assert "Hallo" in docs[0]["content"] and "Welt" in docs[0]["content"]
    assert docs[0]["source_type"] == "Confluence"
    assert docs[0]["storage_key"] == "DOCS/123"


@pytest.mark.anyio
async def test_confluence_connector_skips_unchanged_page_since_last_sync(db_session, test_source):
    test_source.last_synced_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    db_session.add(
        DocumentChunk(
            project_id=test_source.project_id,
            source_id=test_source.id,
            file_path="DOCS/123",
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

    with patch_http(mock_get):
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

    with patch_http(mock_get):
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

    with patch_http(mock_get):
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


# --- Server/Data Center, Pfaderkennung, Wiederholungen (On-Prem) -----------------------------

import httpx  # noqa: E402


def _response(url, status=200, payload=None):
    return httpx.Response(status, json=payload if payload is not None else {}, request=httpx.Request("GET", url))


def _server_handler(calls, pages):
    """Confluence Server/DC: nur /rest/api existiert, /wiki/... liefert 404."""

    async def handler(url, **kwargs):
        calls.append(url)
        if "/wiki/" in url:
            return _response(url, 404)
        if url.endswith("/rest/api/space"):
            return _response(url, 200, {"results": []})
        if "child/attachment" in url:
            return _response(url, 200, {"results": []})
        return _response(url, 200, {"results": pages, "_links": {}})

    return handler


@pytest.mark.anyio
async def test_server_dc_uses_rest_api_without_waiting_on_the_cloud_path(db_session, test_source, monkeypatch):
    test_source.url = "https://wiki.intern/confluence"
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    calls = []
    with patch_http(_server_handler(calls, [_page()])):
        docs = [doc async for doc in connector.fetch_documents()]

    assert len(docs) == 1
    # Regression: früher 15 s Backoff je Listen- und Anhangsabruf, weil /wiki/... erst fünfmal wiederholt wurde.
    assert sum(sleeps) < 1
    assert not any("/wiki/" in url for url in calls)
    assert connector._api_root == "/rest/api"


@pytest.mark.anyio
async def test_cloud_is_detected_by_its_wiki_prefix(db_session, test_source):
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    async def handler(url, **kwargs):
        if "/wiki/rest/api/" not in url:
            return _response(url, 404)
        if url.endswith("/space"):
            return _response(url, 200, {"results": []})
        if "child/attachment" in url:
            return _response(url, 200, {"results": []})
        return _response(url, 200, {"results": [_page()], "_links": {}})

    with patch_http(handler):
        docs = [doc async for doc in connector.fetch_documents()]

    assert len(docs) == 1 and connector._api_root == "/wiki/rest/api"


@pytest.mark.anyio
async def test_rejected_credentials_give_a_clear_error(db_session, test_source):
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    async def handler(url, **kwargs):
        return _response(url, 401)

    with patch_http(handler):
        with pytest.raises(RuntimeError, match="Anmeldung abgelehnt"):
            [doc async for doc in connector.fetch_documents()]


@pytest.mark.anyio
async def test_unknown_url_reports_where_it_looked(db_session, test_source):
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    async def handler(url, **kwargs):
        return _response(url, 404)

    with patch_http(handler):
        with pytest.raises(RuntimeError, match="Kontextpfad"):
            [doc async for doc in connector.fetch_documents()]


@pytest.mark.anyio
async def test_a_failing_page_request_aborts_instead_of_ending_the_crawl_silently(db_session, test_source):
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    async def handler(url, **kwargs):
        if url.endswith("/rest/api/space"):
            return _response(url, 200, {"results": []})
        return _response(url, 403)

    with patch_http(handler):
        with pytest.raises(httpx.HTTPStatusError):
            [doc async for doc in connector.fetch_documents()]


# --- Schlüssel, Aufräumen, Space-Filter, Anhänge ---------------------------------------------

def _chunk(source, key, page_id=None, content="x"):
    return DocumentChunk(
        project_id=source.project_id, source_id=source.id, file_path=key, content=content,
        start_line=1, end_line=1, embedding=[0.0] * 1024,
        metadata_json={"page_id": page_id} if page_id else {},
    )


def _paths(db_session, source):
    return {k for (k,) in db_session.query(DocumentChunk.file_path).filter(DocumentChunk.source_id == source.id).distinct()}


@pytest.mark.anyio
async def test_same_title_in_two_spaces_gets_two_keys(db_session, test_source):
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source
    other = _page(title="Runbook")
    other["id"] = "456"
    other["space"] = {"key": "OPS"}
    calls = []
    with patch_http(_server_handler(calls, [_page(), other])):
        docs = [doc async for doc in connector.fetch_documents()]
    assert sorted(doc["storage_key"] for doc in docs) == ["DOCS/123", "OPS/456"]


@pytest.mark.anyio
async def test_legacy_title_keyed_chunks_move_to_the_new_key_when_the_page_id_matches(db_session, test_source):
    test_source.last_synced_at = datetime(2026, 7, 15, tzinfo=timezone.utc)
    db_session.add_all([_chunk(test_source, "Runbook", page_id="123"), _chunk(test_source, "Runbook", page_id="999")])
    db_session.commit()
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source
    with patch_http(_server_handler([], [_page(when="2026-07-01T10:00:00.000Z")])):
        docs = [doc async for doc in connector.fetch_documents()]
    # Chunk der Seite 123 zog um (unverändert -> übersprungen), der fremde Chunk blieb liegen.
    assert docs == []
    assert _paths(db_session, test_source) == {"DOCS/123", "Runbook"}


@pytest.mark.anyio
async def test_deleted_pages_are_removed_after_a_complete_crawl(db_session, test_source):
    db_session.add_all([_chunk(test_source, "DOCS/123"), _chunk(test_source, "DOCS/777")])
    db_session.commit()
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source
    connector.db = db_session
    with patch_http(_server_handler([], [_page()])):
        [doc async for doc in connector.fetch_documents()]
    assert connector._crawl_complete is True
    assert connector._remove_orphans(connector._seen_keys) == 1
    db_session.expire_all()
    assert _paths(db_session, test_source) == {"DOCS/123"}


@pytest.mark.anyio
async def test_nothing_is_removed_when_the_crawl_found_no_pages_or_too_many_would_vanish(db_session, test_source):
    db_session.add_all([_chunk(test_source, f"DOCS/{i}") for i in range(30)])
    db_session.commit()
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source
    assert connector._remove_orphans(set()) == 0
    assert connector._remove_orphans({"DOCS/1"}) == 0  # 29 von 30 würden verschwinden
    db_session.expire_all()
    assert len(_paths(db_session, test_source)) == 30


@pytest.mark.anyio
async def test_failed_attachment_listing_marks_the_crawl_incomplete(db_session, test_source):
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    async def handler(url, **kwargs):
        if url.endswith("/rest/api/space"):
            return _response(url, 200, {"results": []})
        if "child/attachment" in url:
            return _response(url, 403)
        return _response(url, 200, {"results": [_page()], "_links": {}})

    with patch_http(handler):
        docs = [doc async for doc in connector.fetch_documents()]
    assert len(docs) == 1 and connector._crawl_complete is False


@pytest.mark.anyio
async def test_each_selected_space_is_requested_from_the_server(db_session, test_source):
    test_source.spaces = ["DOCS", "OPS"]
    db_session.commit()
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source
    seen_space_keys = []

    async def handler(url, **kwargs):
        if url.endswith("/rest/api/space"):
            return _response(url, 200, {"results": []})
        if "child/attachment" in url:
            return _response(url, 200, {"results": []})
        key = (kwargs.get("params") or {}).get("spaceKey")
        seen_space_keys.append(key)
        page = _page(title=f"Seite {key}")
        page["id"] = key
        page["space"] = {"key": key}
        return _response(url, 200, {"results": [page], "_links": {}})

    with patch_http(handler):
        docs = [doc async for doc in connector.fetch_documents()]
    assert seen_space_keys == ["DOCS", "OPS"] and len(docs) == 2


@pytest.mark.anyio
async def test_attachments_are_listed_across_pages_and_keyed_by_id(db_session, test_source):
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source
    first = [{"id": f"a{i}", "title": f"f{i}.txt", "metadata": {"mediaType": "text/plain"},
              "_links": {"download": f"/download/{i}"}, "version": {"when": "2026-07-20T00:00:00.000Z"}} for i in range(50)]
    second = [{"id": "a50", "title": "letzte.txt", "metadata": {"mediaType": "text/plain"},
               "_links": {"download": "/download/50"}, "version": {"when": "2026-07-20T00:00:00.000Z"}}]

    async def handler(url, **kwargs):
        if url.endswith("/rest/api/space"):
            return _response(url, 200, {"results": []})
        if "child/attachment" in url:
            start = (kwargs.get("params") or {}).get("start", 0)
            return _response(url, 200, {"results": first if start == 0 else second, "_links": {"next": "x"} if start == 0 else {}})
        if "/download/" in url:
            return httpx.Response(200, content=b"inhalt", request=httpx.Request("GET", url))
        return _response(url, 200, {"results": [_page()], "_links": {}})

    with patch_http(handler):
        docs = [doc async for doc in connector.fetch_documents()]
    keys = {doc["storage_key"] for doc in docs}
    assert "DOCS/123/attachments/a50" in keys and len(keys) == 52  # Seite + 51 Anhänge


# --- Leseeinschränkungen ---------------------------------------------------------------------

def _restricted_page(title="Geheim", page_id="900"):
    page = _page(title=title)
    page["id"] = page_id
    page["restrictions"] = {"read": {"restrictions": {"user": {"results": [{"username": "chef"}]}, "group": {"results": []}}}}
    return page


@pytest.mark.anyio
async def test_restricted_pages_are_skipped_by_default_and_requested_with_their_restrictions(db_session, test_source):
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source
    expands = []

    async def handler(url, **kwargs):
        if url.endswith("/rest/api/space"):
            return _response(url, 200, {"results": []})
        if "child/attachment" in url:
            return _response(url, 200, {"results": []})
        expands.append((kwargs.get("params") or {}).get("expand"))
        return _response(url, 200, {"results": [_page(), _restricted_page()], "_links": {}})

    with patch_http(handler):
        docs = [doc async for doc in connector.fetch_documents()]

    assert [doc["title"] for doc in docs] == ["Runbook"]
    assert "restrictions.read.restrictions.user" in expands[0]
    assert connector._skipped_restricted == 1
    assert "DOCS/900" not in connector._seen_keys  # zählt nicht als vorhanden: bereits Indiziertes wird aufgeräumt


@pytest.mark.anyio
async def test_restricted_pages_can_be_included_explicitly(db_session, test_source):
    test_source.spaces = {"ids": ["ALL"], "include_restricted": True}
    db_session.commit()
    connector = ConfluenceConnector(test_source.id)
    connector.source = test_source

    with patch_http(_server_handler([], [_page(), _restricted_page()])):
        docs = [doc async for doc in connector.fetch_documents()]
    assert {doc["title"] for doc in docs} == {"Runbook", "Geheim"}
