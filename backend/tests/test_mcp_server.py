from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

import mcp_server
from models.database import (
    CodeEntity,
    CodeEdge,
    DocumentChunk,
    KnowledgeSource,
    MCPAccessToken,
    Project,
    ProjectMembership,
    Team,
    TeamMembership,
    User,
)
from services.mcp_tokens import create_token, find_token_user
from services.call_flow import CALL_FLOW_MAX_EDGES, trace_call_flow
from services import ollama_client


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
    foreign_team = Team(name=f"mcp-foreign-team-{suffix}")
    db_session.add_all([owner, outsider, team, foreign_team])
    db_session.flush()

    project = Project(name=f"MCP Test Project {suffix}", team_id=team.id, creator_id=owner.id)
    foreign_project = Project(
        name=f"MCP Foreign Project {suffix}", team_id=foreign_team.id, creator_id=outsider.id
    )
    db_session.add_all([project, foreign_project])
    db_session.flush()
    db_session.add_all(
        [
            TeamMembership(user_id=owner.id, team_id=team.id),
            ProjectMembership(project_id=project.id, user_id=owner.id, role="admin"),
        ]
    )
    db_session.commit()

    yield owner, outsider, project.id, foreign_project.id

    db_session.query(DocumentChunk).filter(
        DocumentChunk.project_id.in_([project.id, foreign_project.id])
    ).delete(synchronize_session=False)
    db_session.query(KnowledgeSource).filter(
        KnowledgeSource.project_id.in_([project.id, foreign_project.id])
    ).delete(synchronize_session=False)
    db_session.query(CodeEntity).filter(CodeEntity.project_id == project.id).delete(
        synchronize_session=False
    )
    db_session.query(MCPAccessToken).filter(
        MCPAccessToken.user_id.in_([owner.id, outsider.id])
    ).delete(synchronize_session=False)
    db_session.query(ProjectMembership).filter(ProjectMembership.project_id == project.id).delete(
        synchronize_session=False
    )
    db_session.query(Project).filter(Project.id.in_([project.id, foreign_project.id])).delete(
        synchronize_session=False
    )
    db_session.query(TeamMembership).filter(TeamMembership.team_id.in_([team.id, foreign_team.id])).delete(
        synchronize_session=False
    )
    db_session.query(Team).filter(Team.id.in_([team.id, foreign_team.id])).delete(
        synchronize_session=False
    )
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
    user, _outsider, project_id, _foreign_project_id = mcp_project_context
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
    user, _outsider, project_id, _foreign_project_id = mcp_project_context

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
    _owner, outsider, project_id, _foreign_project_id = mcp_project_context

    with pytest.raises(ValueError, match="MCP request failed or access denied"):
        mcp_server.search_code(_context(outsider.id), project_id=project_id, query="CARDDEMO")


@pytest.mark.parametrize("direction", ["outgoing", "incoming", "both"])
def test_get_call_flow_accepts_documented_directions(
    db_session, mcp_project_context, monkeypatch, direction
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign_project_id = mcp_project_context
    calls = {}
    requested_root = SimpleNamespace(
        id=1, name="root", qualified_name="root", type="program", file_path="root.cbl",
        source_id=None, start_line=1, end_line=2,
    )
    monkeypatch.setattr(mcp_server, "_entity", lambda *_args: requested_root)

    def fake_trace(_db, **kwargs):
        calls.update(kwargs)
        return {"status": "ok", "nodes": [], "edges": [], "entry_candidates": []}

    monkeypatch.setattr(mcp_server, "trace_call_flow", fake_trace)
    result = mcp_server.get_call_flow(
        _context(user.id), project_id=project_id, entity_id=1, direction=direction
    )

    assert calls["direction"] == direction
    assert result["status"] == "ok"


def test_get_call_flow_includes_bounded_source_evidence_and_binds_cursor_options(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign_project_id = mcp_project_context
    root = CodeEntity(
        project_id=project_id,
        name="root",
        type="method",
        file_path="src/Flow.java",
        qualified_name="demo.Flow#root()",
        start_line=1,
        end_line=12,
    )
    target = CodeEntity(
        project_id=project_id,
        name="callee",
        type="method",
        file_path="src/Flow.java",
        qualified_name="demo.Flow#callee()",
        start_line=20,
        end_line=22,
    )
    db_session.add_all([root, target])
    db_session.flush()
    db_session.add(DocumentChunk(
        project_id=project_id,
        source_id=None,
        file_path="src/Flow.java",
        content="".join(f"line {line}\n" for line in range(1, 13)),
        start_line=1,
        end_line=12,
        metadata_json={},
    ))
    db_session.commit()

    root_node = {
        "id": root.id,
        "name": root.name,
        "qualified_name": root.qualified_name,
        "type": root.type,
        "file_path": root.file_path,
        "source_id": None,
        "start_line": root.start_line,
        "end_line": root.end_line,
    }
    target_node = {
        "id": target.id,
        "name": target.name,
        "qualified_name": target.qualified_name,
        "type": target.type,
        "file_path": target.file_path,
        "source_id": None,
        "start_line": target.start_line,
        "end_line": target.end_line,
    }
    monkeypatch.setattr(
        mcp_server,
        "trace_call_flow",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "root": root_node,
            "nodes": [root_node, target_node],
            "edges": [
                {
                    "id": 1, "source": root.id, "target": target.id,
                    "target_name": "callee", "type": "CALL",
                    "resolution": "resolved", "start_line": 6, "end_line": 6,
                },
                {
                    "id": 2, "source": root.id, "target": target.id,
                    "target_name": "callee", "type": "CALL",
                    "resolution": "resolved", "start_line": 9, "end_line": 9,
                },
            ],
            "entry_candidates": [],
        },
    )

    first = mcp_server.get_call_flow(
        _context(user.id), project_id=project_id, entity_id=root.id, page_size=1
    )
    excerpt = first["edges"][0]["source_excerpt"]
    assert excerpt["focus_line"] == 6
    assert excerpt["delivered_start_line"] <= 6 <= excerpt["delivered_end_line"]
    assert "line 6" in excerpt["content"]
    assert excerpt["chunk_id"] is not None
    assert first["next_cursor"]

    with pytest.raises(ValueError, match="cursor does not match"):
        mcp_server.get_call_flow(
            _context(user.id), project_id=project_id, entity_id=root.id,
            page_size=1, cursor=first["next_cursor"], include_source=False,
        )

    with pytest.raises(ValueError, match="Retry with the next_cursor"):
        mcp_server.get_call_flow(
            _context(user.id), project_id=project_id, entity_id=root.id,
            page_size=1, cursor=first["next_cursor"][:-3] + "!!!",
        )


def test_call_flow_schema_documents_bounds():
    tool = mcp_server.mcp._tool_manager.get_tool("get_call_flow")
    props = tool.parameters["properties"]
    assert "clamped to 15" in props["page_size"]["description"]
    assert "clamped to 3" in props["hops"]["description"]
    assert "unchanged" in props["cursor"]["description"]


@pytest.mark.asyncio
async def test_search_knowledge_uses_the_active_embedding_profile(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign_project_id = mcp_project_context
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
async def test_search_knowledge_falls_back_to_scoped_keywords_when_embedding_fails(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, foreign_project_id = mcp_project_context
    db_session.add_all([
        DocumentChunk(project_id=project_id, file_path="own/a.txt",
                      content="The zorblax settlement runs nightly.", embedding_dimension=1024),
        DocumentChunk(project_id=foreign_project_id, file_path="foreign/b.txt",
                      content="Foreign zorblax secret.", embedding_dimension=1024),
    ])
    db_session.commit()
    profile = SimpleNamespace(
        model="test-embedding", provider="ollama", base_url="https://embedding.test",
        path="/api/embed", api_key=None, dimension=1024, context_length=4096,
    )
    monkeypatch.setattr(mcp_server, "get_active_embedding_profile", lambda _db: profile)

    async def failing_search(*_args, **_kwargs):
        request = httpx.Request("POST", "https://embedding.test/api/embed")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("upstream failure", request=request, response=response)

    monkeypatch.setattr(mcp_server, "search_project_chunks", failing_search)

    result = await mcp_server.search_knowledge(
        _context(user.id), project_id=project_id, query="zorblax settlement"
    )
    assert result["retrieval_mode"] == "lexical_fallback"
    assert "keyword match" in result["notice"]
    paths = [r["file_path"] for r in result["results"]]
    assert paths == ["own/a.txt"]


@pytest.mark.asyncio
async def test_search_knowledge_retrieval_is_scoped_before_ranking(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, foreign_project_id = mcp_project_context
    project = db_session.query(Project).filter(Project.id == project_id).one()
    source = KnowledgeSource(
        name="MCP scoped test source", type="Git", project_id=project_id, team_id=project.team_id
    )
    db_session.add(source)
    db_session.flush()
    vector = [1.0] + [0.0] * 1023
    allowed_legacy_chunk = DocumentChunk(
        project_id=None,
        source_id=source.id,
        file_path="allowed/legacy.txt",
        content="ALLOWED_LEGACY_CHUNK",
        embedding=vector,
        embedding_dimension=1024,
        embedding_model="mcp-test-model",
    )
    foreign_source_less_chunk = DocumentChunk(
        project_id=foreign_project_id,
        source_id=None,
        file_path="foreign/private.txt",
        content="FOREIGN_PRIVATE_SENTINEL",
        embedding=vector,
        embedding_dimension=1024,
        embedding_model="mcp-test-model",
    )
    db_session.add_all([allowed_legacy_chunk, foreign_source_less_chunk])
    db_session.commit()

    profile = SimpleNamespace(
        model="mcp-test-model",
        provider="ollama",
        base_url="https://embedding.test",
        path="/api/embed",
        api_key=None,
        dimension=1024,
        context_length=4096,
    )
    monkeypatch.setattr(mcp_server, "get_active_embedding_profile", lambda _db: profile)
    monkeypatch.setattr(ollama_client, "embed_text", AsyncMock(return_value=vector))

    chunks = await ollama_client.search_project_chunks(
        db_session, project_id, "synthetic query", limit=8, embedding_model="mcp-test-model"
    )
    assert [chunk.id for chunk in chunks] == [allowed_legacy_chunk.id]

    result = await mcp_server.search_knowledge(
        _context(user.id), project_id=project_id, query="synthetic query", limit=8
    )
    assert [item["chunk_id"] for item in result["results"]] == [allowed_legacy_chunk.id]
    assert all("FOREIGN_PRIVATE_SENTINEL" not in item["content"] for item in result["results"])


@pytest.mark.asyncio
async def test_search_knowledge_rechecks_scope_on_retriever_results(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, foreign_project_id = mcp_project_context
    profile = SimpleNamespace(
        model="mcp-test-model",
        provider="ollama",
        base_url="https://embedding.test",
        path="/api/embed",
        api_key=None,
        dimension=1024,
        context_length=4096,
    )
    monkeypatch.setattr(mcp_server, "get_active_embedding_profile", lambda _db: profile)
    foreign_chunk = SimpleNamespace(
        id=987654, project_id=foreign_project_id, source_id=None,
        file_path="foreign/private.txt", start_line=1, end_line=2,
        content="FOREIGN_PRIVATE_SENTINEL",
    )

    async def faulty_retriever(*_args, **_kwargs):
        return [foreign_chunk]

    monkeypatch.setattr(mcp_server, "search_project_chunks", faulty_retriever)
    result = await mcp_server.search_knowledge(
        _context(user.id), project_id=project_id, query="synthetic query"
    )
    assert result["results"] == []


def test_call_flow_bounds_edges_before_returning_them(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    _owner, _outsider, project_id, _foreign_project_id = mcp_project_context
    root = CodeEntity(
        # Paragraph statt program: ein COBOL-program ohne Einstiegs-Paragraph liefert
        # bewusst entry_point_not_found (O-343) -- hier geht es nur um die Kantengrenze.
        project_id=project_id, name="BusyRoot", type="paragraph", file_path="busy.cbl"
    )
    db_session.add(root)
    db_session.commit()
    db_session.add_all([
        CodeEdge(
            project_id=project_id,
            src_entity_id=root.id,
            dst_entity_id=root.id,
            dst_name="BusyRoot",
            type="CALL",
            resolution="resolved",
        )
        for _ in range(CALL_FLOW_MAX_EDGES + 37)
    ])
    db_session.commit()

    result = trace_call_flow(
        db_session, project_id=project_id, entity_id=root.id, hops=1
    )
    assert len(result["edges"]) == CALL_FLOW_MAX_EDGES
    assert result["truncated"] is True


def test_mcp_token_revocation_takes_effect_immediately(db_session, mcp_project_context):
    user, _outsider, _project_id, _foreign_project_id = mcp_project_context
    token, secret = create_token(db_session, user=user, name="MCP server test", days=30)
    assert find_token_user(db_session, secret).id == user.id

    token.revoked_at = datetime.now(timezone.utc)
    db_session.commit()
    assert find_token_user(db_session, secret) is None
    assert token.revoked_at is not None


def test_get_code_entity_continuation_keeps_later_chunks(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign_project_id = mcp_project_context
    entity = CodeEntity(
        project_id=project_id, name="big", type="method", file_path="src/Big.java",
        qualified_name="demo.Big#big()", start_line=1, end_line=12,
    )
    db_session.add(entity)
    db_session.flush()
    for index in range(4):
        db_session.add(DocumentChunk(
            project_id=project_id, source_id=None, file_path="src/Big.java",
            content=f"{index}" * 600, start_line=index * 3 + 1, end_line=index * 3 + 3,
            metadata_json={},
        ))
    db_session.commit()

    seen = []
    chunk_id, char_offset = None, 0
    for _ in range(10):
        result = mcp_server.get_code_entity(
            _context(user.id), project_id=project_id, entity_id=entity.id,
            max_chars=500, chunk_id=chunk_id, char_offset=char_offset,
        )
        seen += [(s["chunk_id"], len(s["content"])) for s in result["definition"]["sections"]]
        definition = result["definition"]
        if not definition["truncated"]:
            break
        chunk_id, char_offset = definition["next_chunk_id"], definition["next_char_offset"]
    assert sum(length for _cid, length in seen) == 2400
    assert len({cid for cid, _length in seen}) == 4

    with pytest.raises(ValueError, match="invalid cursor"):
        mcp_server.get_code_entity(
            _context(user.id), project_id=project_id, entity_id=entity.id, chunk_id=-5,
        )


def test_research_project_uses_paged_call_flow_contract(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign_project_id = mcp_project_context
    root = CodeEntity(
        project_id=project_id, name="resolveWidget", type="method", file_path="src/W.java",
        qualified_name="demo.W#resolveWidget()", start_line=1, end_line=5,
    )
    db_session.add(root)
    db_session.flush()
    db_session.add(DocumentChunk(
        project_id=project_id, source_id=None, file_path="src/W.java",
        content="".join(f"line {n}\n" for n in range(1, 6)), start_line=1, end_line=5,
        metadata_json={},
    ))
    db_session.commit()
    root_node = {
        "id": root.id, "name": root.name, "qualified_name": root.qualified_name,
        "type": root.type, "file_path": root.file_path, "source_id": None,
        "start_line": 1, "end_line": 5,
    }
    edges = [
        {"id": n, "source": root.id, "target": None, "target_name": f"x{n}", "type": "CALL",
         "resolution": "unresolved", "start_line": 2, "end_line": 2}
        for n in range(1, 31)
    ]
    monkeypatch.setattr(
        mcp_server, "trace_call_flow",
        lambda *_a, **_k: {"status": "ok", "root": root_node, "nodes": [root_node],
                           "edges": edges, "entry_candidates": []},
    )

    result = mcp_server.research_project(_context(user.id), project_id=project_id, query="resolveWidget")
    flow = result["call_flow"]
    assert result["resolution"] == "unique_exact_match"
    assert len(flow["edges"]) == 10
    assert flow["has_more"] and flow["next_cursor"]
    assert flow["edges"][0]["source_excerpt"]["chunk_id"] is not None
    assert flow["follow_up_actions"][0]["tool"] == "get_call_flow"


def test_research_terms_keep_prose_but_split_symbol_lists():
    terms = mcp_server._research_terms
    assert terms("how does approval/decline work") == ["how does approval/decline work"]
    assert terms("UserLogic#create(User) UserLogic#update(UserPatch)") == [
        "UserLogic#create(User)", "UserLogic#update(UserPatch)"
    ]
    assert terms("CARD-INCIDENT PA-TRANSACTION-AMT") == ["CARD-INCIDENT", "PA-TRANSACTION-AMT"]
    assert terms("src/Foo.java src/Bar.java") == ["src/Foo.java", "src/Bar.java"]


def test_research_project_prose_without_symbol_offers_code_and_knowledge_search(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign_project_id = mcp_project_context
    result = mcp_server.research_project(
        _context(user.id), project_id=project_id, query="how does approval/decline work"
    )
    assert result["resolution"] == "no_exact_match"
    assert [a["tool"] for a in result["follow_up_actions"]] == ["search_code", "search_knowledge"]
