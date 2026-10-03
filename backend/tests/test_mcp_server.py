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
    # v2: kompakter Flow ohne Quellauszug je Kante; die Quelle kommt über explain_symbol.
    assert "source_excerpt" not in flow["edges"][0]
    assert flow["follow_up_actions"][0]["tool"] == "get_call_flow"
    assert result["follow_up_actions"][0]["tool"] == "explain_symbol"


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


def _method(project_id, name, qualified, path="src/Auth.java", start=1, end=6, kind="method"):
    return CodeEntity(
        project_id=project_id, name=name, type=kind, file_path=path,
        qualified_name=qualified, start_line=start, end_line=end,
    )


def _chunk(project_id, path, lines, start=1):
    return DocumentChunk(
        project_id=project_id, source_id=None, file_path=path,
        content="".join(f"{text}\n" for text in lines), start_line=start,
        end_line=start + len(lines) - 1, metadata_json={},
    )


def test_query_variants_cover_the_java_method_spelling():
    variants = mcp_server._query_variants("AuthDataAccessor.authenticate")
    assert "AuthDataAccessor#authenticate" in variants
    assert mcp_server._query_variants("org.x.Auth.run(String)")[:1] == ["org.x.Auth.run(String)"]
    assert "Auth#run" in mcp_server._query_variants("org.x.Auth.run")
    assert mcp_server._query_variants("COSGN00C.MAIN-PARA") == ["COSGN00C.MAIN-PARA"]


def test_search_code_finds_java_methods_by_dotted_name_and_word_pairs(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    method = _method(project_id, "authenticate", "org.demo.AuthDataAccessor#authenticate(Authentication)")
    db_session.add(method)
    db_session.commit()

    dotted = mcp_server.search_code(_context(user.id), project_id=project_id, query="AuthDataAccessor.authenticate")
    assert [hit["id"] for hit in dotted["results"]] == [method.id]
    assert dotted["resolution"] == "exact"

    words = mcp_server.search_code(_context(user.id), project_id=project_id, query="authenticate AuthDataAccessor")
    assert [hit["id"] for hit in words["results"]] == [method.id]
    assert words["resolution"] == "fuzzy"


def test_search_code_suggests_similar_names_when_nothing_matches(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    db_session.add(_method(project_id, "authenticate", "org.demo.AuthDataAccessor#authenticate(Authentication)"))
    db_session.commit()

    result = mcp_server.search_code(_context(user.id), project_id=project_id, query="AuthDataAccessor.unknownThing")
    assert result["results"] == [] and result["resolution"] == "none"
    assert result["did_you_mean"][0]["qualified_name"].endswith("AuthDataAccessor#authenticate(Authentication)")


def test_search_code_compact_adds_source_only_for_the_best_exact_match(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    first = _method(project_id, "run", "demo.Job#run()", "src/Job.java", 1, 3)
    second = _method(project_id, "run", "demo.Other#run()", "src/Other.java", 1, 3)
    db_session.add_all([first, second, _chunk(project_id, "src/Job.java", ["a", "b", "c"]),
                        _chunk(project_id, "src/Other.java", ["x", "y", "z"])])
    db_session.commit()

    compact = mcp_server.search_code(_context(user.id), project_id=project_id, query="run")
    with_source = [hit for hit in compact["results"] if "source_excerpt" in hit]
    assert len(with_source) == 1 and "analysis" not in compact["results"][0]
    assert compact["results"][0]["location"].endswith(".java:1-3")
    assert compact["follow_up_actions"][0]["tool"] == "explain_symbol"
    assert "detail" not in str(mcp_server.search_code.__doc__)


def test_search_code_hides_parameters_unless_they_match_exactly(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    method = _method(project_id, "login", "demo.Auth#login(String)")
    param = _method(project_id, "login", "demo.Auth#login(String)@param:loginName", kind="parameter")
    db_session.add_all([method, param])
    db_session.commit()
    result = mcp_server.search_code(_context(user.id), project_id=project_id, query="Auth#login", include_source=False)
    assert [hit["type"] for hit in result["results"]] == ["method"]


def test_explain_symbol_returns_numbered_source_callers_callees_and_data_access(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    target = _method(project_id, "authenticate", "org.demo.Auth#authenticate(String)", "src/Auth.java", 10, 13)
    caller = _method(project_id, "login", "org.demo.Provider#login()", "src/Provider.java", 1, 4)
    db_session.add_all([target, caller])
    db_session.flush()
    db_session.add_all([
        _chunk(project_id, "src/Auth.java", ["m(String u) {", "  check(u);", "  return ok;", "}"], 10),
        CodeEdge(project_id=project_id, src_entity_id=target.id, dst_entity_id=None, dst_name="check", type="CALLS",
                 resolution="unresolved", src_start_line=11, src_end_line=11),
        CodeEdge(project_id=project_id, src_entity_id=target.id, dst_entity_id=None, dst_name="failedLogins", type="WRITES",
                 resolution="resolved", src_start_line=12, src_end_line=12, meta_json={"operation": "SET"}),
    ])
    db_session.commit()
    root = {"id": target.id, "name": target.name, "qualified_name": target.qualified_name, "type": "method",
            "file_path": target.file_path, "source_id": None, "start_line": 10, "end_line": 13}
    caller_node = {"id": caller.id, "name": "login", "qualified_name": caller.qualified_name, "type": "method",
                   "file_path": caller.file_path, "source_id": None, "start_line": 1, "end_line": 4}

    def fake_flow(_db, *, direction, **_kwargs):
        if direction == "incoming":
            edge = {"id": 1, "source": caller.id, "target": target.id, "target_name": "authenticate", "type": "CALLS",
                    "resolution": "resolved", "start_line": 2, "end_line": 2}
            return {"status": "ok", "root": root, "nodes": [root, caller_node], "edges": [edge], "entry_candidates": []}
        edge = {"id": 2, "source": target.id, "target": None, "target_name": "check", "type": "CALLS",
                "resolution": "unresolved", "start_line": 11, "end_line": 11}
        return {"status": "ok", "root": root, "nodes": [root], "edges": [edge], "entry_candidates": []}

    monkeypatch.setattr(mcp_server, "trace_call_flow", fake_flow)
    result = mcp_server.explain_symbol(_context(user.id), project_id=project_id, symbol="Auth.authenticate")

    assert result["resolution"] == "unique_exact_match"
    assert result["source"]["text"].splitlines()[1] == "11:   check(u);"
    assert result["callers"][0]["from"] == caller.qualified_name
    assert result["callees"][0]["to"] == "check"
    assert result["data_access"][0]["target"] == "failedLogins" and result["data_access"][0]["operation"] == "SET"
    assert "outline" not in result


def test_explain_symbol_returns_an_outline_with_facts_when_the_source_exceeds_the_budget(
    db_session, mcp_project_context, monkeypatch
):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    program = _method(project_id, "BIGPROG", "BIGPROG", "app/BIGPROG.cbl", 1, 400, kind="program")
    first = _method(project_id, "READ-FILE", "BIGPROG.READ-FILE", "app/BIGPROG.cbl", 10, 30, kind="paragraph")
    second = _method(project_id, "WRITE-FILE", "BIGPROG.WRITE-FILE", "app/BIGPROG.cbl", 31, 60, kind="paragraph")
    db_session.add_all([program, first, second])
    db_session.flush()
    db_session.add_all([
        _chunk(project_id, "app/BIGPROG.cbl", ["X" * 80 for _ in range(400)], 1),
        CodeEdge(project_id=project_id, src_entity_id=first.id, dst_entity_id=None, dst_name="XREF-FILE", type="READS",
                 resolution="resolved", src_start_line=12, src_end_line=12,
                 meta_json={"io_target_kind": "file_fd", "operation": "READ"}),
        CodeEdge(project_id=project_id, src_entity_id=second.id, dst_entity_id=None, dst_name="NEXT-PARA", type="PERFORM",
                 resolution="resolved", src_start_line=40, src_end_line=40),
    ])
    db_session.commit()

    result = mcp_server.explain_symbol(_context(user.id), project_id=project_id, symbol="BIGPROG", max_chars=2000)
    assert "source" not in result
    symbols = {item["symbol"]: item for item in result["outline"]}
    assert symbols["BIGPROG.READ-FILE"]["facts"] == "io READ XREF-FILE"
    assert symbols["BIGPROG.WRITE-FILE"]["facts"] == "performs NEXT-PARA"
    assert symbols["BIGPROG.READ-FILE"]["lines"] == "10-30"

    ranged = mcp_server.explain_symbol(_context(user.id), project_id=project_id, symbol="BIGPROG.READ-FILE", start_line=10, end_line=12)
    assert ranged["source"]["start_line"] == 10 and "outline" not in ranged


def test_explain_symbol_reports_unknown_and_ambiguous_symbols(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    db_session.add_all([
        _method(project_id, "create", "a.One#create()", "src/One.java", 1, 3),
        _method(project_id, "create", "b.Two#create()", "src/Two.java", 1, 3),
        _method(project_id, "create", "b.TwoTest#create()", "src/test/TwoTest.java", 1, 3),
    ])
    db_session.commit()

    unknown = mcp_server.explain_symbol(_context(user.id), project_id=project_id, symbol="Nothing.here")
    assert unknown["resolution"] == "none" and "hint" in unknown
    ambiguous = mcp_server.explain_symbol(_context(user.id), project_id=project_id, symbol="create")
    assert ambiguous["resolution"] == "ambiguous"
    assert {c["qualified_name"] for c in ambiguous["candidates"]} == {"a.One#create()", "b.Two#create()", "b.TwoTest#create()"}


def test_explain_symbol_denies_a_project_the_mcp_user_cannot_open(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    _owner, outsider, project_id, _foreign = mcp_project_context
    with pytest.raises(ValueError, match="MCP request failed or access denied"):
        mcp_server.explain_symbol(_context(outsider.id), project_id=project_id, symbol="anything")


def test_get_code_entity_resolves_a_symbol_without_an_entity_id(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    entity = _method(project_id, "run", "demo.Job#run()", "src/Job.java", 1, 2)
    db_session.add_all([entity, _chunk(project_id, "src/Job.java", ["a", "b"])])
    db_session.commit()

    result = mcp_server.get_code_entity(_context(user.id), project_id=project_id, symbol="Job.run")
    assert result["id"] == entity.id and result["definition"]["sections"]
    with pytest.raises(ValueError, match="entity_id or symbol required"):
        mcp_server.get_code_entity(_context(user.id), project_id=project_id)


def test_extract_symbols_finds_code_names_in_german_and_english_questions():
    extract = mcp_server._extract_symbols
    assert extract("In AWS CardDemo: Wie berechnet das Batch-Programm CBACT04C die Zinsen?") == ["CardDemo", "CBACT04C"]
    assert "DefaultNotificationManager.createTasks" in extract("Wie erzeugt DefaultNotificationManager.createTasks Aufgaben?")
    assert "DefaultNotificationManager" not in extract("Wie erzeugt DefaultNotificationManager.createTasks Aufgaben?")
    terms = extract("Welche Programme binden das Copybook CVTRA05Y ein? Feld TRAN-RECORD, z.B. TRAN-ID.")
    assert "CVTRA05Y" in terms and "TRAN-RECORD" in terms and "TRAN-ID" in terms and "z.B" not in terms
    assert extract("Wie funktioniert das eigentlich?") == []


def test_relevant_children_prefers_names_and_facts_that_match_the_question():
    outline = [
        {"symbol": "P.WORKING-STORAGE", "type": "section", "lines": "1-9"},
        {"symbol": "P.1000-READ-INPUT", "type": "paragraph", "lines": "10-20", "facts": "io READ INFILE"},
        {"symbol": "P.1300-COMPUTE-INTEREST", "type": "paragraph", "lines": "21-30", "facts": "performs 1300-B-WRITE-TX"},
        {"symbol": "P.9999-ABEND-PROGRAM", "type": "paragraph", "lines": "31-40"},
    ]
    top = mcp_server._relevant_children("Wie berechnet P die Zinsen und welche Formel gilt?", outline, 2)
    assert top[0]["symbol"] == "P.1300-COMPUTE-INTEREST"
    assert all(item["type"] != "section" for item in top)
    files = mcp_server._relevant_children("Welche Dateien werden gelesen?", outline, 1)
    assert files[0]["symbol"] == "P.1000-READ-INPUT"


def test_used_by_lists_copy_users_and_overload_callers_once_per_unit(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    book = _method(project_id, "CVBOOK", "CVBOOK", "app/cpy/CVBOOK.cpy", 1, 5, kind="copybook")
    prog_a = _method(project_id, "PROGA", "PROGA", "app/cbl/PROGA.cbl", 1, 90, kind="program")
    prog_b = _method(project_id, "PROGB", "PROGB", "app/cbl/PROGB.cbl", 1, 90, kind="program")
    own = _method(project_id, "CVBOOK2", "CVBOOK.CVBOOK", "app/cpy/CVBOOK.cpy", 2, 3, kind="program")
    db_session.add_all([book, prog_a, prog_b, own])
    db_session.flush()
    db_session.add_all([
        CodeEdge(project_id=project_id, src_entity_id=prog_a.id, dst_entity_id=book.id, dst_name="CVBOOK", type="COPY", resolution="resolved", src_start_line=7, src_end_line=7),
        CodeEdge(project_id=project_id, src_entity_id=prog_a.id, dst_entity_id=book.id, dst_name="CVBOOK", type="COPY", resolution="resolved", src_start_line=40, src_end_line=40),
        CodeEdge(project_id=project_id, src_entity_id=prog_b.id, dst_entity_id=book.id, dst_name="CVBOOK", type="COPY", resolution="resolved", src_start_line=9, src_end_line=9),
        CodeEdge(project_id=project_id, src_entity_id=own.id, dst_entity_id=book.id, dst_name="CVBOOK", type="COPY", resolution="resolved", src_start_line=3, src_end_line=3),
    ])
    db_session.commit()
    users = mcp_server._used_by(db_session, db_session.get(User, user.id), book, 10)
    assert [u["unit"] for u in users] == ["PROGA", "PROGB"]
    assert users[0]["lines"] == [7, 40] and users[0]["types"] == ["COPY"]


def test_answer_context_resolves_named_symbols_and_returns_evidence(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    method = _method(project_id, "authenticate", "org.demo.Auth#authenticate(String)", "src/Auth.java", 1, 3)
    db_session.add_all([method, _chunk(project_id, "src/Auth.java", ["check(u);", "return ok;", "}"])])
    db_session.commit()
    monkeypatch.setattr(mcp_server, "trace_call_flow", lambda *_a, **_k: {
        "status": "ok", "root": None, "nodes": [], "edges": [], "entry_candidates": []})

    result = mcp_server.answer_context(
        _context(user.id), project_id=project_id,
        question="Wie läuft Auth.authenticate ab und welche Prüfungen gibt es?")
    assert [r["symbol"] for r in result["resolved"]] == ["org.demo.Auth#authenticate(String)"]
    assert result["evidence"][0]["source"]["text"].splitlines()[0] == "1: check(u);"


def test_answer_context_expands_the_paragraphs_that_match_a_large_program(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    program = _method(project_id, "BIGPROG", "BIGPROG", "app/BIGPROG.cbl", 1, 300, kind="program")
    interest = _method(project_id, "1300-COMPUTE-INTEREST", "BIGPROG.1300-COMPUTE-INTEREST", "app/BIGPROG.cbl", 100, 110, kind="paragraph")
    other = _method(project_id, "9999-ABEND", "BIGPROG.9999-ABEND", "app/BIGPROG.cbl", 200, 210, kind="paragraph")
    db_session.add_all([program, interest, other,
                        _chunk(project_id, "app/BIGPROG.cbl", [("L%03d " % n) + "x" * 70 for n in range(1, 301)], 1)])
    db_session.commit()
    monkeypatch.setattr(mcp_server, "trace_call_flow", lambda *_a, **_k: {
        "status": "ok", "root": None, "nodes": [], "edges": [], "entry_candidates": []})

    result = mcp_server.answer_context(
        _context(user.id), project_id=project_id,
        question="Wie berechnet BIGPROG die Zinsen?", max_chars=6000)
    entry = result["evidence"][0]
    assert "source" not in entry and entry["outline"]
    assert entry["expanded"][0]["symbol"] == "BIGPROG.1300-COMPUTE-INTEREST"
    assert entry["expanded"][0]["source"]["text"].splitlines()[0].startswith("100: L100")


def test_answer_context_without_a_symbol_offers_candidates(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    result = mcp_server.answer_context(_context(user.id), project_id=project_id, question="Wie funktioniert die Anmeldung?")
    assert result["resolved"] == [] and "hint" in result


def test_answer_context_denies_a_project_the_mcp_user_cannot_open(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    _owner, outsider, project_id, _foreign = mcp_project_context
    with pytest.raises(ValueError, match="MCP request failed or access denied"):
        mcp_server.answer_context(_context(outsider.id), project_id=project_id, question="Was macht CBACT04C?")


@pytest.fixture(autouse=True)
def _no_embedding_calls(monkeypatch):
    monkeypatch.setattr(mcp_server, "_embedding_scores", lambda *_a, **_k: None)


def test_answer_context_accepts_symbols_and_topic_without_a_question(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    method = _method(project_id, "authenticate", "org.demo.Auth#authenticate(String)", "src/Auth.java", 1, 3)
    db_session.add_all([method, _chunk(project_id, "src/Auth.java", ["check(u);", "return ok;", "}"])])
    db_session.commit()
    monkeypatch.setattr(mcp_server, "trace_call_flow", lambda *_a, **_k: {
        "status": "ok", "root": None, "nodes": [], "edges": [], "entry_candidates": []})

    result = mcp_server.answer_context(_context(user.id), project_id=project_id,
                                       symbols=["Auth.authenticate"], topic="login checks")
    assert [r["symbol"] for r in result["resolved"]] == ["org.demo.Auth#authenticate(String)"]
    assert result["unresolved_terms"] == []


def test_answer_context_follows_the_call_chain_two_hops(db_session, mcp_project_context, monkeypatch):
    _use_test_session(monkeypatch, db_session)
    user, _outsider, project_id, _foreign = mcp_project_context
    a = _method(project_id, "start", "org.demo.Entry#start()", "src/Entry.java", 1, 3)
    b = _method(project_id, "route", "org.demo.Router#route()", "src/Router.java", 1, 8)
    c = _method(project_id, "deliver", "org.demo.Sender#deliver()", "src/Sender.java", 1, 3)
    db_session.add_all([a, b, c, _chunk(project_id, "src/Entry.java", ["route();", "x;", "}"]),
                        _chunk(project_id, "src/Router.java", ["deliver();", "y;", "z;", "w;", "v;", "u;", "t;", "}"])])
    db_session.commit()

    def flow(_db, _user, _project, entity_id, **kwargs):
        if kwargs["direction"] == "incoming":
            return {"nodes": [], "edges": []}
        target = {a.id: b, b.id: c}.get(entity_id)
        if target is None:
            return {"nodes": [], "edges": []}
        return {"nodes": [{"id": target.id, "qualified_name": target.qualified_name, "file_path": target.file_path,
                           "start_line": target.start_line}],
                "edges": [{"target": target.id, "type": "CALLS", "start_line": 1}]}

    monkeypatch.setattr(mcp_server, "_call_flow_page", flow)
    result = mcp_server.answer_context(_context(user.id), project_id=project_id, symbols=["Entry.start"], topic="routing")
    chain = result["evidence"][0]["callee_chain"]
    assert chain[0]["symbol"] == "org.demo.Router#route()"
    assert chain[0]["source"]["text"].startswith("1: deliver();")
    assert chain[0]["calls"] == ["Sender#deliver (Zeile 1)"]


def test_embedding_scores_blend_into_the_ranking(db_session, mcp_project_context, monkeypatch):
    user, _outsider, project_id, _foreign = mcp_project_context
    monkeypatch.setattr(mcp_server, "_embedding_scores", lambda _db, _p, _q, texts: [0.1 if "PLAIN" in t else 0.9 for t in texts])
    rows = [(1.0, {"symbol": "PLAIN-ONE"}), (1.0, {"symbol": "SEMANTIC-TWO"})]
    ranked = mcp_server._rank_by_embedding(db_session, project_id, "q", rows, lambda i: i["symbol"])
    assert ranked[0][1]["symbol"] == "SEMANTIC-TWO"


def test_chat_prefetch_runs_the_evidence_pack_and_registers_citable_sources(db_session, mcp_project_context, monkeypatch):
    import asyncio
    import agent
    from api import chat as chat_api

    user, _outsider, project_id, _foreign = mcp_project_context
    method = _method(project_id, "authenticate", "org.demo.Auth#authenticate(String)", "src/Auth.java", 1, 3)
    db_session.add_all([method, _chunk(project_id, "src/Auth.java", ["check(u);", "return ok;", "}"])])
    db_session.commit()
    monkeypatch.setattr(mcp_server, "trace_call_flow", lambda *_a, **_k: {
        "status": "ok", "root": None, "nodes": [], "edges": [], "entry_candidates": []})

    prompt = "Context...\nQuestion: Wie läuft Auth.authenticate ab?"
    prefetched = asyncio.run(agent._prefetch_evidence(db_session, user.id, project_id, prompt))
    name, args, raw = prefetched
    assert name == "answer_context" and args["symbols"] == ["org.demo.Auth#authenticate(String)"]

    sources: list = []
    chat_api._extract_tool_sources({"type": "tool_result", "name": name, "result": raw}, sources, 7)
    assert {"file": "src/Auth.java", "lines": [1, 3], "source_id": 7} in sources

    # Unknown symbols fall back to the regular bootstrap.
    assert asyncio.run(agent._prefetch_evidence(db_session, user.id, project_id, "Question: Was ist Zebra?")) is None


def test_outline_facts_carry_message_texts_and_assigned_codes(db_session, mcp_project_context):
    _user, _outsider, project_id, _foreign = mcp_project_context
    program = _method(project_id, "AUTHPROG", "AUTHPROG", "app/AUTHPROG.cbl", 1, 12, kind="program")
    para = _method(project_id, "8000-DECLINE", "AUTHPROG.8000-DECLINE", "app/AUTHPROG.cbl", 3, 8, kind="paragraph")
    lines = ["       PROCEDURE DIVISION.", "      * comment 'not a message at all'",
             "       8000-DECLINE.", "           MOVE '51' TO AUTH-RESP-REASON",
             "           DISPLAY 'INSUFFICIENT FUNDS (LIMIT)'", "           MOVE 'N' TO FLAG", "           EXIT.",
             "", "", "", "", ""]
    db_session.add_all([program, para, _chunk(project_id, "app/AUTHPROG.cbl", lines)])
    db_session.commit()
    outline = mcp_server._outline(db_session, program)
    facts = next(item for item in outline if item["symbol"] == "AUTHPROG.8000-DECLINE")["facts"]
    assert "AUTH-RESP-REASON=51" in facts and '"INSUFFICIENT FUNDS [LIMIT]"' in facts
    assert "not a message" not in facts


def test_evidence_budget_scales_with_the_context_window():
    from api.chat import _evidence_budget
    assert _evidence_budget(None) is None
    assert _evidence_budget(8192) == 5538
    assert _evidence_budget(2048) == 3000 and _evidence_budget(131072) == 14000


def test_relevant_children_follows_perform_one_step_and_skips_housekeeping():
    outline = [
        {"symbol": "P.0000-FILE-OPEN", "type": "paragraph", "lines": "1-5", "facts": "io OPEN INFILE"},
        {"symbol": "P.1300-COMPUTE-INTEREST", "type": "paragraph", "lines": "6-9", "facts": "performs 1300-B-WRITE-TX, 9999-ABEND-PROGRAM"},
        {"symbol": "P.1300-B-WRITE-TX", "type": "paragraph", "lines": "10-20", "facts": 'io WRITE TRANFILE; msgs "Int. for a/c"'},
        {"symbol": "P.9999-ABEND-PROGRAM", "type": "paragraph", "lines": "21-30", "facts": "calls CEE3ABD"},
    ]
    chosen = [c["symbol"] for c in mcp_server._relevant_children("Wie berechnet P die Zinsen?", outline, 1)]
    assert chosen == ["P.1300-COMPUTE-INTEREST", "P.1300-B-WRITE-TX"]


def test_outline_facts_name_the_fields_a_paragraph_computes(db_session, mcp_project_context):
    _user, _outsider, project_id, _foreign = mcp_project_context
    program = _method(project_id, "INTPROG", "INTPROG", "app/INTPROG.cbl", 1, 9, kind="program")
    para = _method(project_id, "1300-COMPUTE-INTEREST", "INTPROG.1300-COMPUTE-INTEREST", "app/INTPROG.cbl", 2, 6, kind="paragraph")
    lines = ["       PROCEDURE DIVISION.", "       1300-COMPUTE-INTEREST.", "           COMPUTE WS-MONTHLY-INT",
             "            = (BAL * RATE) / 1200", "           ADD WS-MONTHLY-INT TO WS-TOTAL-INT", "           EXIT.", "", "", ""]
    db_session.add_all([program, para, _chunk(project_id, "app/INTPROG.cbl", lines)])
    db_session.commit()
    facts = next(i for i in mcp_server._outline(db_session, program) if i["symbol"].endswith("COMPUTE-INTEREST"))["facts"]
    assert "computes WS-MONTHLY-INT, WS-TOTAL-INT" in facts


def test_ide_file_marks_known_system_targets_as_external(unauthenticated_client, db_session, mcp_project_context):
    """O-325: ein COPY auf ein MQ-Systemcopybook ist `unresolved`, aber extern und keine Indexlücke."""
    from models.database import CodeEdge

    owner, _outsider, project_id, _foreign = mcp_project_context
    source = KnowledgeSource(name="ide-src", type="Git", project_id=project_id, team_id=db_session.query(Project.team_id).filter(Project.id == project_id).scalar())
    db_session.add(source)
    db_session.flush()
    program = CodeEntity(project_id=project_id, source_id=source.id, file_path="cbl/PROG.cbl", name="PROG",
                         qualified_name="PROG", type="program", start_line=1, end_line=30)
    db_session.add(program)
    db_session.flush()
    for name, meta in (("CMQODV", {"external": {"category": "mq", "kind": "system_copybook"}}), ("MYBOOK", {})):
        db_session.add(CodeEdge(project_id=project_id, source_id=source.id, src_entity_id=program.id, dst_name=name,
                                type="COPY", resolution="unresolved", src_start_line=10, src_end_line=10, meta_json=meta))
    db_session.commit()
    _token, secret = create_token(db_session, user=owner, name="ide external", days=1)

    response = unauthenticated_client.get(
        "/ide/file", params={"project_id": project_id, "source_id": source.id, "path": "cbl/PROG.cbl"},
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200
    by_name = {ref["name"]: ref for ref in response.json()["references"]}
    assert by_name["CMQODV"]["external_category"] == "mq" and by_name["CMQODV"]["resolution"] == "unresolved"
    assert by_name["MYBOOK"]["external_category"] is None


def test_data_access_summary_lists_the_dataset_assigned_through_a_jcl_dd(db_session, mcp_project_context):
    """O-147: `ASSIGNED_DATASET` erscheint in der Datenzugriffsübersicht mit DD-Name und JCL-Fundstelle."""
    from models.database import CodeEdge

    _owner, _outsider, project_id, _foreign = mcp_project_context
    source = KnowledgeSource(name="dd-src", type="Git", project_id=project_id, team_id=db_session.query(Project.team_id).filter(Project.id == project_id).scalar())
    db_session.add(source)
    db_session.flush()

    def entity(type_, name, path, start, end, parent=None):
        item = CodeEntity(project_id=project_id, source_id=source.id, file_path=path, name=name, qualified_name=name,
                          type=type_, start_line=start, end_line=end, parent_id=parent.id if parent else None)
        db_session.add(item)
        db_session.flush()
        return item

    program = entity("program", "CBTRN02C", "cbl/CBTRN02C.cbl", 1, 90)
    file_fd = entity("file_fd", "TRANSACT-FILE", "cbl/CBTRN02C.cbl", 30, 31, parent=program)
    dataset = entity("jcl_dataset", "AWS.TRANSACT.KSDS", "jcl/POSTTRAN.jcl", 14, 14)
    db_session.add(CodeEdge(
        project_id=project_id, source_id=source.id, src_entity_id=file_fd.id, dst_entity_id=dataset.id,
        dst_name=dataset.name, type="ASSIGNED_DATASET", resolution="resolved", src_start_line=30, src_end_line=31,
        meta_json={"derived_by": "jcl_dd_assign", "ddname": "TRANFILE", "jcl_file_path": "jcl/POSTTRAN.jcl", "jcl_start_line": 14},
    ))
    db_session.commit()

    summary = mcp_server._data_access_summary(db_session, program)

    assert summary == [{
        "access": "ASSIGNED_DATASET", "target": "AWS.TRANSACT.KSDS", "lines": [30],
        "ddname": "TRANFILE", "via_jcl": "jcl/POSTTRAN.jcl:14", "certainty": "possible",
    }]
