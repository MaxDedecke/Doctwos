"""Webansicht: gemeinsames Format, nur Indexiertes, Rückfall auf den Index, Links und Bilder."""

import uuid
from types import SimpleNamespace

import httpx
import pytest
import respx
from fastapi import HTTPException

from doctus_models.database import DocumentChunk, KnowledgeSource, Project, Team
from services import web_documents
from services.web_documents import resolve as web
from services.web_documents.base import WebAdapter
from services.web_documents.confluence import ConfluenceAdapter
from services.web_documents.jira import JiraAdapter, _adf_to_html

JIRA = "https://jira.example/jira"
WIKI = "https://wiki.example/confluence"
USER = SimpleNamespace(id=1)


@pytest.fixture
def sources(db_session, monkeypatch):
    monkeypatch.setattr(web, "source_visible", lambda db, user, source_id: True)
    team = Team(name=f"web-documents-{uuid.uuid4().hex[:8]}")
    db_session.add(team)
    db_session.flush()
    project = Project(name="web-documents", team_id=team.id)
    db_session.add(project)
    db_session.flush()

    def source(kind, url):
        row = KnowledgeSource(
            name=kind, type=kind, url=url, project_id=project.id, team_id=team.id, token="geheim"
        )
        db_session.add(row)
        db_session.flush()
        return row

    def chunk(row, key, content="Indexierter Text", **meta):
        db_session.add(
            DocumentChunk(
                project_id=project.id,
                source_id=row.id,
                file_path=key,
                content=content,
                start_line=1,
                end_line=1,
                metadata_json=meta,
            )
        )
        db_session.flush()

    jira, wiki = source("Jira", JIRA), source("Confluence", WIKI)
    chunk(jira, "ABC-1", title="ABC-1: Fehler", url=f"{JIRA}/browse/ABC-1")
    chunk(jira, "ABC-2", title="ABC-2: Anderes", url=f"{JIRA}/browse/ABC-2")
    chunk(wiki, "ENG/123", title="Runbook", url=f"{WIKI}/display/ENG/Runbook")
    chunk(wiki, "ENG/456", title="Notfall", url=f"{WIKI}/pages/viewpage.action?pageId=456")
    chunk(
        wiki,
        "ENG/123/attachments/9",
        "Text aus dem Anhang",
        title="Runbook — plan.pdf",
        url=f"{WIKI}/download/attachments/123/plan.pdf",
    )
    db_session.commit()
    return SimpleNamespace(jira=jira, wiki=wiki, chunk=chunk, source=source)


def _issue(**fields):
    return {
        "fields": {
            "summary": "Fehler <b>x</b>",
            "status": {"name": "Open"},
            "priority": None,
            "assignee": None,
            "reporter": {"displayName": "Ada"},
            "issuetype": {"name": "Bug"},
            "labels": ["cobol"],
            "components": [{"name": "Batch"}],
            "created": "2026-01-02T10:00:00.000+0000",
            "description": "{code}roh{code}",
            "comment": {
                "total": 1,
                "comments": [{"author": None, "created": "2026-01-03", "body": "*fett*"}],
            },
            "issuelinks": [
                {
                    "type": {"outward": "blocks", "inward": "is blocked by"},
                    "outwardIssue": {
                        "key": "ABC-2",
                        "fields": {"summary": "Anderes", "status": {"name": "Done"}},
                    },
                },
                {"type": {"outward": "blocks"}, "outwardIssue": {"key": "XYZ-9", "fields": {}}},
            ],
            "attachment": [
                {
                    "filename": "log.txt",
                    "content": f"{JIRA}/secure/attachment/1/log.txt",
                    "size": 12,
                }
            ],
            **fields,
        },
        "renderedFields": {
            "description": '<pre class="code-java">sauber</pre>'
            f'<a href="{JIRA}/browse/ABC-2">ABC-2</a><a href="https://example.org/x">extern</a>'
            '<img src="/jira/images/a.png" srcset="b 2x">',
            "comment": {"comments": [{"body": "<b>fett</b>"}]},
        },
    }


@respx.mock
def test_ticket_uses_rendered_html_all_facts_and_marks_known_links(db_session, sources):
    respx.get(f"{JIRA}/rest/api/2/issue/ABC-1").mock(return_value=httpx.Response(200, json=_issue()))

    result = web.resolve_web_document(db_session, USER, sources.jira, f"{JIRA}/browse/ABC-1", True)

    assert result["format"] == "web_document" and result["url"] == f"{JIRA}/browse/ABC-1"
    doc = result["document"]
    assert doc["title"] == "Fehler <b>x</b>" and doc["identifier"] == "ABC-1"
    assert doc["origin"] == "live" and doc["notice"] is None
    facts = {fact["key"]: fact["values"] for fact in doc["facts"]}
    assert facts["type"] == ["Bug"] and facts["reporter"] == ["Ada"]
    assert facts["labels"] == ["cobol"] and facts["components"] == ["Batch"]
    assert "priority" not in facts and "assignee" not in facts
    # Gerendertes HTML statt Wiki-Text.
    assert "sauber" in doc["body_html"] and "{code}" not in doc["body_html"]
    assert doc["comments"][0]["body_html"] == "<b>fett</b>"
    # Bekanntes Ticket derselben Quelle: öffnet in Doctus. Unbekanntes und Fremdes bleibt ein Link.
    assert f'data-doctus-source="{sources.jira.id}"' in doc["body_html"]
    assert 'href="https://example.org/x">' in doc["body_html"]
    related = {item["identifier"]: item for item in doc["related"]}
    assert related["ABC-2"]["source_id"] == sources.jira.id and related["ABC-2"]["status"] == "Done"
    assert related["XYZ-9"]["source_id"] is None
    # Bilder und Anhänge laufen signiert über den Server.
    assert "web-asset?token=" in doc["body_html"] and "srcset" not in doc["body_html"]
    attachment = doc["attachments"][0]["url"]
    assert attachment.startswith(f"/knowledge-sources/{sources.jira.id}/web-asset?token=")


@respx.mock
def test_ticket_without_rendered_fields_escapes_wiki_text_and_adf(db_session, sources):
    issue = _issue()
    issue.pop("renderedFields")
    respx.get(f"{JIRA}/rest/api/2/issue/ABC-1").mock(return_value=httpx.Response(404))
    respx.get(f"{JIRA}/rest/api/3/issue/ABC-1").mock(return_value=httpx.Response(200, json=issue))

    doc = web.resolve_web_document(db_session, USER, sources.jira, "ABC-1", True)["document"]

    assert doc["body_html"] == "{code}roh{code}"
    assert doc["comments"][0]["body_html"] == "*fett*"
    html = _adf_to_html(
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "<x>", "marks": [{"type": "code"}]},
                {
                    "type": "text",
                    "text": "L",
                    "marks": [{"type": "link", "attrs": {"href": 'http://a/"b'}}],
                },
            ],
        }
    )
    assert html == '<p><code>&lt;x&gt;</code><a href="http://a/&quot;b">L</a></p>'


def _page(page_id="123"):
    return {
        "id": page_id,
        "title": "Runbook",
        "_links": {"webui": "/display/ENG/Runbook", "base": WIKI},
        "space": {"name": "Engineering"},
        "version": {"number": 7, "when": "2026-02-01T10:00:00Z", "by": {"displayName": "Ada"}},
        "history": {"createdBy": {"displayName": "Bob"}, "createdDate": "2020-01-01T10:00:00Z"},
        "metadata": {"labels": {"results": [{"name": "ops"}]}},
        "ancestors": [{"id": "456", "title": "Notfall"}, {"id": "999", "title": "Gesperrt"}],
        "body": {
            "view": {
                "value": '<a href="#a">Oben</a><a href="/confluence/pages/viewpage.action?pageId=456">N</a>'
                f'<a href="{JIRA}/browse/ABC-1">T</a>'
                "<img src='/confluence/download/thumbnails/123/x.png?v=1&amp;api=v2'/>"
            }
        },
    }


@respx.mock
def test_page_has_title_path_comments_attachments_and_links_across_sources(db_session, sources):
    api = f"{WIKI}/rest/api/content/123"
    respx.get(api).mock(return_value=httpx.Response(200, json=_page()))
    respx.get(f"{api}/child/comment").mock(
        return_value=httpx.Response(
            200,
            json={
                "size": 1,
                "results": [
                    {
                        "history": {"createdBy": {"displayName": "Eve"}, "createdDate": "2026-03-01"},
                        "body": {"view": {"value": "<p>gut</p>"}},
                    }
                ],
            },
        )
    )
    respx.get(f"{api}/child/attachment").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "plan.pdf",
                        "_links": {"download": "/download/attachments/123/plan.pdf"},
                        "extensions": {"fileSize": 5, "mediaType": "application/pdf"},
                    }
                ]
            },
        )
    )

    doc = web.resolve_web_document(db_session, USER, sources.wiki, f"{WIKI}/display/ENG/Runbook", True)[
        "document"
    ]

    assert doc["title"] == "Runbook" and doc["kind"] == "page"
    assert doc["url"] == f"{WIKI}/display/ENG/Runbook"
    facts = {fact["key"]: fact["values"] for fact in doc["facts"]}
    assert facts["space"] == ["Engineering"] and facts["version"] == ["7"]
    assert facts["labels"] == ["ops"] and facts["author"] == ["Bob"]
    assert doc["comments"][0]["author"] == "Eve" and doc["comments_total"] == 1
    # Sprungmarken bleiben, relative Links werden absolut, auch Links zu einer anderen Quelle sind bekannt.
    assert '<a href="#a">' in doc["body_html"]
    assert f'data-doctus-source="{sources.wiki.id}"' in doc["body_html"]
    assert f'data-doctus-source="{sources.jira.id}"' in doc["body_html"]
    assert "web-asset?token=" in doc["body_html"] and doc["body_html"].endswith("/>")
    crumbs = {crumb["title"]: crumb["source_id"] for crumb in doc["breadcrumbs"]}
    assert crumbs == {"Notfall": sources.wiki.id, "Gesperrt": None}
    url, name = web.read_asset_token(
        sources.wiki.id, doc["attachments"][0]["url"].split("token=")[1]
    )
    assert url == f"{WIKI}/download/attachments/123/plan.pdf" and name == "plan.pdf"


@respx.mock
def test_page_survives_failing_comments(db_session, sources):
    api = f"{WIKI}/rest/api/content/123"
    respx.get(api).mock(return_value=httpx.Response(200, json=_page()))
    respx.get(f"{api}/child/comment").mock(return_value=httpx.Response(500))

    doc = web.resolve_web_document(db_session, USER, sources.wiki, "ENG/123", True)["document"]

    assert doc["origin"] == "live" and doc["comments"] == []


@pytest.mark.parametrize(
    "kind,reference",
    [("jira", f"{JIRA}/browse/GEHEIM-1"), ("wiki", f"{WIKI}/pages/viewpage.action?pageId=777")],
)
@respx.mock
def test_what_the_index_does_not_hold_is_never_fetched(db_session, sources, kind, reference):
    with pytest.raises(HTTPException) as caught:
        web.resolve_web_document(db_session, USER, getattr(sources, kind), reference, True)
    assert caught.value.status_code == 404
    assert not respx.calls


@respx.mock
def test_foreign_host_is_rejected_without_a_request(db_session, sources):
    with pytest.raises(HTTPException):
        web.resolve_web_document(db_session, USER, sources.jira, "https://evil.example/browse/ABC-1", True)
    assert not respx.calls


@respx.mock
def test_unreachable_source_falls_back_to_the_index(db_session, sources):
    respx.get(url__startswith=f"{JIRA}/rest/").mock(side_effect=httpx.ConnectError("weg"))

    doc = web.resolve_web_document(db_session, USER, sources.jira, "ABC-1", True)["document"]

    assert doc["origin"] == "index" and doc["notice"] == "unreachable"
    assert doc["title"] == "ABC-1: Fehler" and "Indexierter Text" in doc["body_html"]


@respx.mock
def test_attachment_entry_shows_its_indexed_text_without_a_request(db_session, sources):
    doc = web.resolve_web_document(
        db_session, USER, sources.wiki, f"{WIKI}/download/attachments/123/plan.pdf", True
    )["document"]

    assert doc["notice"] == "index_only" and "Text aus dem Anhang" in doc["body_html"]
    assert not respx.calls


@respx.mock
def test_any_new_system_works_from_its_index_without_an_adapter(db_session, sources):
    row = sources.source("ServiceNow", "https://snow.example")
    sources.chunk(row, "INC-1", "<b>Text</b>\n\nZweiter Absatz", title="INC-1", url="https://snow.example/i/1")
    db_session.commit()

    assert isinstance(web_documents.adapter_for("ServiceNow"), WebAdapter)
    doc = web.resolve_web_document(db_session, USER, row, "https://snow.example/i/1", True)["document"]

    assert doc["notice"] == "index_only" and not respx.calls
    assert doc["body_html"] == "<p>&lt;b&gt;Text&lt;/b&gt;</p><p>Zweiter Absatz</p>"


def test_a_new_adapter_only_needs_a_registry_entry(db_session, sources, monkeypatch):
    class Snow(WebAdapter):
        def index_key(self, url):
            return url.rsplit("/", 1)[-1]

        def fetch(self, ctx, key, meta):
            return web.WebDocument(title=f"Live {key}", url=meta["url"], kind="incident")

    monkeypatch.setitem(web_documents.ADAPTERS, "servicenow", Snow())
    row = sources.source("ServiceNow", "https://snow.example")
    sources.chunk(row, "INC-1", title="INC-1", url="https://snow.example/i/INC-1")
    db_session.commit()

    doc = web.resolve_web_document(db_session, USER, row, "https://snow.example/i/INC-1", True)["document"]

    assert doc["title"] == "Live INC-1" and doc["kind"] == "incident"


def test_file_sources_are_not_web_sources(db_session, sources):
    for kind in ("Git", "Local", "FolderWatch", "WebDAV"):
        assert not web_documents.is_web_source(kind)
    row = sources.source("Git", "https://git.example")
    with pytest.raises(HTTPException) as caught:
        web.resolve_web_document(db_session, USER, row, "x", True)
    assert caught.value.status_code == 400


def test_asset_token_is_bound_to_its_source_and_must_be_genuine():
    token = web.asset_url(5, f"{WIKI}/a.png").split("token=")[1]
    assert web.read_asset_token(5, token) == (f"{WIKI}/a.png", None)
    for source_id, value in ((6, token), (5, token + "x")):
        with pytest.raises(HTTPException) as caught:
            web.read_asset_token(source_id, value)
        assert caught.value.status_code == 403


@respx.mock
def test_asset_sends_credentials_only_to_the_own_instance(sources):
    respx.get(f"{WIKI}/a.png").mock(
        return_value=httpx.Response(302, headers={"location": "https://evil.example/a.png"})
    )
    with pytest.raises(HTTPException) as caught:
        web.open_asset(sources.wiki, f"{WIKI}/a.png", True)
    assert caught.value.status_code == 403
    assert len(respx.calls) == 1
    with pytest.raises(HTTPException):
        web.open_asset(sources.wiki, "https://evil.example/a.png", True)
    assert len(respx.calls) == 1


@respx.mock
def test_asset_follows_redirects_inside_the_instance(sources):
    respx.get(f"{WIKI}/a.png").mock(
        return_value=httpx.Response(302, headers={"location": "/confluence/b.png"})
    )
    respx.get(f"{WIKI}/b.png").mock(
        return_value=httpx.Response(200, content=b"x", headers={"content-type": "image/png"})
    )
    client, response = web.open_asset(sources.wiki, f"{WIKI}/a.png", True)
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert respx.calls[-1].request.headers["authorization"] == "Bearer geheim"
    response.close()
    client.close()


def test_url_patterns():
    assert JiraAdapter().index_key(f"{JIRA}/browse/abc-1#x") == "ABC-1"
    assert JiraAdapter().index_key(f"{JIRA}/secure/Rapid.jspa?selectedIssue=ABC-2") == "ABC-2"
    assert JiraAdapter().index_key(f"{JIRA}/projects/ABC") is None
    assert ConfluenceAdapter().index_key(f"{WIKI}/pages/viewpage.action?pageId=5") == "*/5"
    assert ConfluenceAdapter().index_key(f"{WIKI}/spaces/E/pages/77/Titel") == "*/77"
    assert ConfluenceAdapter().index_key(f"{WIKI}/display/E/Titel") is None
    assert ConfluenceAdapter().index_key(f"{WIKI}/download/attachments/123/x.pdf") is None


@respx.mock
def test_asset_route_needs_no_session_but_a_genuine_token(db_session, sources):
    """Das iframe sendet kein Cookie: Ohne Anmeldung muss der Pfad gehen, ohne Signatur darf er es nicht."""
    from fastapi.testclient import TestClient

    from main import app

    respx.route(host="testserver").pass_through()
    respx.get(f"{WIKI}/a.svg").mock(
        return_value=httpx.Response(200, content=b"<svg/>", headers={"content-type": "image/svg+xml"})
    )
    respx.get(f"{WIKI}/plan.pdf").mock(
        return_value=httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
    )
    client = TestClient(app)
    source_id = sources.wiki.id

    assert client.get(f"/knowledge-sources/{source_id}/web-asset?token=falsch").status_code == 403

    image = client.get(web.asset_url(source_id, f"{WIKI}/a.svg"))
    assert image.status_code == 200 and image.content == b"<svg/>"
    assert "sandbox" in image.headers["content-security-policy"]
    assert image.headers["x-content-type-options"] == "nosniff"

    # Ohne Download-Namen wird nur ein Bild ausgeliefert, ein Anhang nur als Download.
    assert client.get(web.asset_url(source_id, f"{WIKI}/plan.pdf")).status_code == 415
    download = client.get(web.asset_url(source_id, f"{WIKI}/plan.pdf", "plan ü.pdf"))
    assert download.status_code == 200
    assert download.headers["content-disposition"] == "attachment; filename*=UTF-8''plan%20%C3%BC.pdf"

    # Die übrigen Wege der Quelle bleiben hinter der Anmeldung.
    assert client.get(f"/knowledge-sources/{source_id}/resolve?url=x").status_code == 401
