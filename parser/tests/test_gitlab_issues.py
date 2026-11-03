from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from connectors.gitlab_issues import GitLabIssuesConnector

_REAL_CLIENT = httpx.AsyncClient


def connector(monkeypatch, handler, projects=None):
    item = object.__new__(GitLabIssuesConnector)
    item.source = SimpleNamespace(
        url="https://gitlab.intern/context",
        token="test-only",
        spaces={"ids": projects or ["team/sub/project"]},
    )
    item.source_id = 999
    item._log = Mock()
    item._prune = Mock()
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    return item


def issue(iid=1, **extra):
    return {
        "project_id": 7,
        "iid": iid,
        "title": "Payment",
        "description": "Service.create",
        "state": "opened",
        "labels": ["bug"],
        "web_url": f"https://gitlab.intern/context/team/sub/project/-/issues/{iid}",
        **extra,
    }


@pytest.mark.anyio
async def test_paginated_issues_and_comments_use_context_path_and_token(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["PRIVATE-TOKEN"] == "test-only"
        if request.url.path.endswith("/notes"):
            page = request.url.params["page"]
            return httpx.Response(
                200,
                json=[{"id": int(page), "author": {"name": "Ada"}, "body": f"comment {page}"}],
                headers={"X-Next-Page": "2" if page == "1" else ""},
            )
        page = request.url.params["page"]
        return httpx.Response(
            200, json=[issue(int(page))], headers={"X-Next-Page": "2" if page == "1" else ""}
        )

    item = connector(monkeypatch, handler)
    docs = [doc async for doc in item.fetch_documents()]
    assert len(docs) == 2
    assert all("comment 1" in doc["content"] and "comment 2" in doc["content"] for doc in docs)
    assert docs[0]["storage_key"] == "7/issues/1"
    assert all(request.url.path.startswith("/context/api/v4/projects/") for request in seen)
    assert "%2F" in str(seen[0].url)
    item._prune.assert_called_once_with({"7/issues/1", "7/issues/2"})


@pytest.mark.anyio
async def test_confidential_issues_and_internal_system_notes_are_excluded(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/notes"):
            return httpx.Response(
                200,
                json=[
                    {"id": n, "body": body, **flags}
                    for n, body, flags in [
                        (1, "public", {}),
                        (2, "secret", {"internal": True}),
                        (3, "hidden", {"confidential": True}),
                        (4, "event", {"system": True}),
                    ]
                ],
            )
        return httpx.Response(200, json=[issue(), issue(2, confidential=True)])

    item = connector(monkeypatch, handler)
    docs = [doc async for doc in item.fetch_documents()]
    assert len(docs) == 1
    assert "public" in docs[0]["content"]
    assert all(text not in docs[0]["content"] for text in ("secret", "hidden", "event"))


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 404])
async def test_failed_comments_abort_without_deletion(monkeypatch, status):
    def handler(request):
        return (
            httpx.Response(status)
            if request.url.path.endswith("/notes")
            else httpx.Response(200, json=[issue()])
        )

    item = connector(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        _ = [doc async for doc in item.fetch_documents()]
    item._prune.assert_not_called()


@pytest.mark.anyio
async def test_repeated_pagination_aborts_without_deletion(monkeypatch):
    item = connector(
        monkeypatch, lambda req: httpx.Response(200, json=[], headers={"X-Next-Page": "1"})
    )
    with pytest.raises(ValueError, match="advance"):
        _ = [doc async for doc in item.fetch_documents()]
    item._prune.assert_not_called()


@pytest.mark.anyio
async def test_empty_complete_project_can_remove_last_deleted_issue(monkeypatch):
    item = connector(monkeypatch, lambda req: httpx.Response(200, json=[]))
    assert [doc async for doc in item.fetch_documents()] == []
    item._prune.assert_called_once_with(set())


@pytest.mark.anyio
async def test_requires_explicit_projects(monkeypatch):
    item = connector(monkeypatch, lambda req: pytest.fail("unexpected request"), ["ALL"])
    with pytest.raises(ValueError, match="explicit"):
        _ = [doc async for doc in item.fetch_documents()]


@pytest.mark.anyio
async def test_http_import_persistence_comment_edits_and_last_issue_deletion(monkeypatch):
    import json
    import threading
    import uuid
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from unittest.mock import AsyncMock
    from sqlalchemy import text
    from db import SessionLocal
    from doctus_models.database import KnowledgeSource, DocumentChunk

    state = {"issues": [issue()], "body": "original comment"}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers["PRIVATE-TOKEN"] == "test-only"
            data = (
                [{"id": 1, "body": state["body"], "author": {"name": "Ada"}}]
                if "/notes?" in self.path
                else state["issues"]
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Next-Page", "")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        "connectors.base.get_embeddings_batch",
        AsyncMock(side_effect=lambda texts, **kwargs: [[0.01] * 1024 for _ in texts]),
    )
    monkeypatch.setattr("connectors.base.BaseConnector._doc_concurrency", AsyncMock(return_value=1))
    with SessionLocal() as db:
        team = db.execute(
            text("INSERT INTO teams (name,created_at) VALUES (:name,now()) RETURNING id"),
            {"name": f"gitlab-test-{uuid.uuid4().hex}"},
        ).scalar_one()
        source = KnowledgeSource(
            name="GitLab HTTP test",
            type="GitLabIssues",
            url=f"http://127.0.0.1:{server.server_port}",
            token="test-only",
            spaces={"ids": ["7"]},
            team_id=team,
        )
        db.add(source)
        db.commit()
        sid = source.id
    try:

        async def sync():
            await GitLabIssuesConnector(sid).sync()

        await sync()
        with SessionLocal() as db:
            chunks = db.query(DocumentChunk).filter_by(source_id=sid).all()
            assert chunks and "original comment" in "".join(c.content for c in chunks)
            count = len(chunks)
        state["body"] = "edited comment"
        await sync()
        with SessionLocal() as db:
            chunks = db.query(DocumentChunk).filter_by(source_id=sid).all()
            assert len(chunks) == count
            content = "".join(c.content for c in chunks)
            assert "edited comment" in content and "original comment" not in content
        # A newly confidential issue must disappear from the index, even when it was the last one.
        state["issues"] = [issue(confidential=True)]
        await sync()
        with SessionLocal() as db:
            assert db.query(DocumentChunk).filter_by(source_id=sid).count() == 0
            assert db.get(KnowledgeSource, sid).sync_status == "completed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        with SessionLocal() as db:
            db.query(DocumentChunk).filter_by(source_id=sid).delete()
            db.query(KnowledgeSource).filter_by(id=sid).delete()
            db.execute(text("DELETE FROM teams WHERE id=:id"), {"id": team})
            db.commit()
