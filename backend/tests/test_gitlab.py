from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from api import connectors
from api.gitlab import gitlab_base
from api.schemas import ConnectorTestRequest, ConnectorReposRequest, ConnectorBranchesRequest
from services import ai_settings
from core import config as cfg

_REAL_CLIENT = httpx.AsyncClient


@pytest.mark.anyio
async def test_internal_gitlab_test_repos_and_branches_are_paginated(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "gitlab.intern"
        assert request.url.path.startswith("/context/api/v4/")
        assert request.headers["Private-Token"] == "test-only"
        if request.url.path.endswith("/user"):
            return httpx.Response(200, json={"id": 1})
        page = int(request.url.params["page"])
        data = (
            [{"name": f"branch-{page}"}]
            if request.url.path.endswith("/branches")
            else [
                {
                    "name": f"project-{page}",
                    "path_with_namespace": f"team/project-{page}",
                    "http_url_to_repo": f"https://gitlab.intern/context/team/project-{page}.git",
                }
            ]
        )
        return httpx.Response(200, json=data, headers={"X-Next-Page": "2" if page == 1 else ""})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    common = {"type": "gitlab", "url": "https://gitlab.intern/context", "token": "test-only"}
    result = await connectors.test_connector(ConnectorTestRequest(**common))
    assert result["success"]
    result = await connectors.get_connector_repos(ConnectorReposRequest(**common))
    assert len(result) == 2
    result = await connectors.get_connector_branches(
        ConnectorBranchesRequest(**common, repo_name="team/sub/project")
    )
    assert result == ["branch-1", "branch-2"]
    assert len(requests) == 5


@pytest.mark.parametrize(
    "url", ["file:///tmp/gitlab", "https://user:secret@host", "https://host?q=1", "https://host/#x"]
)
def test_gitlab_url_rejects_credentials_and_invalid_schemes(url):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        gitlab_base(url)


def test_fresh_remote_bootstrap_keeps_url_protocol_and_independent_embeddings(monkeypatch):
    monkeypatch.setattr(cfg, "BOOTSTRAP_LLM_ENDPOINT", True)
    monkeypatch.setattr(cfg, "BOOTSTRAP_LLM_PROVIDER", "vllm")
    monkeypatch.setattr(cfg, "BOOTSTRAP_LLM_URL", "http://chat.internal:8001/v1")
    monkeypatch.setattr(cfg, "BOOTSTRAP_LLM_KEY", "test-only")
    db = MagicMock()
    db.query.return_value.order_by.return_value.all.return_value = []
    settings = SimpleNamespace(
        active_profile_id=None,
        llm_model="pilot",
        embedding_model="embed",
        embedding_provider="openai",
        embedding_base_url="http://embed.internal/v1",
        embedding_dimension=1024,
        embedding_context_length=8100,
        llm_context_length=8192,
    )
    profile = ai_settings.ensure_profiles(db, settings)[0]
    assert profile.kind == "remote" and profile.protocol == "openai_chat"
    assert profile.llm_base_url == "http://chat.internal:8001/v1"
    assert profile.llm_path == "/chat/completions"
    assert profile.embedding_base_url == "http://embed.internal/v1"


def test_gitlab_issue_creation_queues_and_resyncs(client, monkeypatch):
    from api import knowledge_sources as api

    sent = []
    monkeypatch.setattr(api, "send_tracked_task", lambda *args, **kwargs: sent.append(args))
    response = client.post(
        "/knowledge-sources",
        json={
            "name": "GitLab pilot",
            "type": "gitlabissues",
            "url": "https://gitlab.intern",
            "token": "test-only",
            "spaces": {"ids": ["team/project"]},
        },
    )
    assert response.status_code == 200, response.text
    source_id = response.json()["id"]
    try:
        assert len(sent) == 1
        assert client.post(f"/knowledge-sources/{source_id}/sync").status_code == 200
        assert len(sent) == 2
    finally:
        client.delete(f"/knowledge-sources/{source_id}")


def test_gitlab_issue_source_requires_project_and_url(client):
    for options in (
        {"url": "https://gitlab.intern", "spaces": ["ALL"]},
        {"spaces": ["team/project"]},
    ):
        assert (
            client.post(
                "/knowledge-sources", json={"name": "bad", "type": "gitlabissues", **options}
            ).status_code
            == 400
        )
