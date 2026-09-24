from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

import mcp_server
from models.database import (
    CodeEntity,
    MCPAccessToken,
    Project,
    ProjectMembership,
    Team,
    TeamMembership,
    User,
)
from services.mcp_tokens import create_token, find_token_user


@pytest.fixture
def mcp_project_context(db_session):
    suffix = uuid4().hex
    owner = User(
        username=f"mcp-owner-{suffix}",
        email=f"mcp-owner-{suffix}@example.test",
        name="MCP Test Owner",
        password_hash="unused-test-hash",
        role="user",
    )
    outsider = User(
        username=f"mcp-outsider-{suffix}",
        email=f"mcp-outsider-{suffix}@example.test",
        name="MCP Test Outsider",
        password_hash="unused-test-hash",
        role="user",
    )
    team = Team(name=f"mcp-team-{suffix}")
    db_session.add_all([owner, outsider, team])
    db_session.flush()

    project = Project(name=f"MCP Test Project {suffix}", team_id=team.id, creator_id=owner.id)
    db_session.add(project)
    db_session.flush()
    db_session.add_all(
        [
            TeamMembership(user_id=owner.id, team_id=team.id),
            ProjectMembership(project_id=project.id, user_id=owner.id, role="admin"),
        ]
    )
    db_session.commit()

    yield owner, outsider, project.id

    db_session.query(CodeEntity).filter(CodeEntity.project_id == project.id).delete(
        synchronize_session=False
    )
    db_session.query(MCPAccessToken).filter(
        MCPAccessToken.user_id.in_([owner.id, outsider.id])
    ).delete(synchronize_session=False)
    db_session.query(ProjectMembership).filter(ProjectMembership.project_id == project.id).delete(
        synchronize_session=False
    )
    db_session.query(Project).filter(Project.id == project.id).delete(synchronize_session=False)
    db_session.query(TeamMembership).filter(TeamMembership.team_id == team.id).delete(
        synchronize_session=False
    )
    db_session.query(Team).filter(Team.id == team.id).delete(synchronize_session=False)
    db_session.query(User).filter(User.id.in_([owner.id, outsider.id])).delete(
        synchronize_session=False
    )
    db_session.commit()


def _context(user_id: int):
    return SimpleNamespace(
        request_context=SimpleNamespace(
            request=SimpleNamespace(scope={"state": {"mcp_user_id": user_id}})
        )
    )


def _use_test_session(monkeypatch, db_session):
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    # _tool_context closes its own session. Keep the fixture's shared session
    # open so fixture teardown can still inspect its ORM objects.
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(mcp_server, "record_mcp_tool_call", lambda *_args, **_kwargs: None)


def test_search_code_matches_qualified_names_and_pipe_alternatives(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id = mcp_project_context
    entities = [
        CodeEntity(
            project_id=project_id,
            name="ConnectorLogic",
            type="program",
            file_path="app/menu.cbl",
            qualified_name="org.example.ConnectorLogic",
        ),
        CodeEntity(
            project_id=project_id,
            name="DefaultNotificationManager",
            type="class",
            file_path="app/account.cpy",
            qualified_name="org.example.DefaultNotificationManager",
        ),
        CodeEntity(
            project_id=project_id,
            name="PullJobDelegate",
            type="class",
            file_path="app/jobs.cpy",
            qualified_name="org.example.PullJobDelegate",
        ),
    ]
    db_session.add_all(entities)
    db_session.commit()
    expected_ids = {entity.id for entity in entities}

    result = mcp_server.search_code(
        _context(user.id),
        project_id=project_id,
        query=("class ConnectorLogic|class DefaultNotificationManager|class PullJobDelegate"),
        limit=10,
    )

    assert {entity["id"] for entity in result["results"]} == expected_ids
    assert len(result["results"]) == len(expected_ids)
    assert all(entity["qualified_name"] for entity in result["results"])


def test_search_code_rejects_queries_with_too_many_alternatives(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id = mcp_project_context

    with pytest.raises(ValueError, match="invalid query"):
        mcp_server.search_code(
            _context(user.id),
            project_id=project_id,
            query="|".join(f"term-{index}" for index in range(13)),
        )


def test_search_code_denies_a_project_the_mcp_user_cannot_open(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    _owner, outsider, project_id = mcp_project_context

    with pytest.raises(ValueError, match="MCP request failed or access denied"):
        mcp_server.search_code(_context(outsider.id), project_id=project_id, query="CARDDEMO")


@pytest.mark.asyncio
async def test_search_knowledge_uses_the_active_embedding_profile(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id = mcp_project_context
    profile = SimpleNamespace(
        model="test-embedding",
        provider="openai",
        base_url="https://embedding.test/v1",
        path="/embeddings",
        api_key="embedding-secret",
        dimension=1024,
        context_length=4096,
    )
    monkeypatch.setattr(mcp_server, "get_active_embedding_profile", lambda _db: profile)
    calls = {}

    async def fake_search(db, project_id, query, **kwargs):
        calls.update(project_id=project_id, query=query, **kwargs)
        return []

    monkeypatch.setattr(mcp_server, "search_project_chunks", fake_search)

    result = await mcp_server.search_knowledge(
        _context(user.id),
        project_id=project_id,
        query="architecture overview",
    )

    assert result["results"] == []
    assert calls == {
        "project_id": project_id,
        "query": "architecture overview",
        "limit": 6,
        "embedding_model": "test-embedding",
        "embedding_provider": "openai",
        "embedding_base_url": "https://embedding.test/v1",
        "embedding_path": "/embeddings",
        "embedding_api_key": "embedding-secret",
        "embedding_dimension": 1024,
        "embedding_context_length": 4096,
    }


@pytest.mark.asyncio
async def test_search_knowledge_reports_upstream_http_status_safely(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id = mcp_project_context
    profile = SimpleNamespace(
        model="test-embedding",
        provider="ollama",
        base_url="https://embedding.test",
        path="/api/embed",
        api_key=None,
        dimension=1024,
        context_length=4096,
    )
    monkeypatch.setattr(mcp_server, "get_active_embedding_profile", lambda _db: profile)

    async def failing_search(*_args, **_kwargs):
        request = httpx.Request("POST", "https://embedding.test/api/embed")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("upstream failure", request=request, response=response)

    monkeypatch.setattr(mcp_server, "search_project_chunks", failing_search)

    with pytest.raises(
        ValueError,
        match="embedding endpoint returned HTTP 404; check the active embedding profile URL and path",
    ):
        await mcp_server.search_knowledge(
            _context(user.id),
            project_id=project_id,
            query="architecture overview",
        )


def test_mcp_token_revocation_takes_effect_immediately(db_session, mcp_project_context):
    user, _outsider, _project_id = mcp_project_context
    token, secret = create_token(db_session, user=user, name="MCP server test", days=30)
    assert find_token_user(db_session, secret).id == user.id

    token.revoked_at = datetime.now(timezone.utc)
    db_session.commit()
    assert find_token_user(db_session, secret) is None
    assert token.revoked_at is not None
