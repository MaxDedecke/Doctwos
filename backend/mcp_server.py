"""Read-only inbound MCP transport and tools for IDE clients."""

import logging
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

import core.config as cfg
from api import entities as entity_api
from api import graph as graph_api
from core.db_setup import SessionLocal
from core.projects import (
    assert_knowledge_source_visible,
    assert_project_visible,
    get_visible_project_ids,
    get_visible_projects_page,
)
from core.teams import get_visible_team_ids
from models.database import CodeEntity, KnowledgeSource, Project, User
from services.call_flow import trace_call_flow
from services.ai_settings import get_active_embedding_profile
from services.mcp_audit import record_mcp_tool_call
from services.mcp_tokens import find_token_user
from services.ollama_client import search_project_chunks
from services.search import search_nodes


logger = logging.getLogger(__name__)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)


def _bounded(value: str | None, limit: int = 1200) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    return value[:limit], len(value) > limit


def _project(db: Session, user: User, project_id: int) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404)
    assert_project_visible(project_id, user, db)
    return project


def _entity(db: Session, user: User, project_id: int, entity_id: int) -> CodeEntity:
    _project(db, user, project_id)
    entity = db.query(CodeEntity).filter(
        CodeEntity.id == entity_id, CodeEntity.project_id == project_id
    ).first()
    if entity is None:
        raise HTTPException(status_code=404)
    entity_api._assert_entity_visible(entity, user, db, project_id)
    return entity


def _source_visible(db: Session, user: User, source_id: int | None) -> bool:
    if source_id is None:
        return True
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if source is None:
        return False
    try:
        assert_knowledge_source_visible(source, user, db)
    except HTTPException:
        return False
    return True


@contextmanager
def _tool_context(ctx: Context, name: str, project_id: int | None, audit_args: dict):
    request = ctx.request_context.request
    user_id = request.scope.get("state", {}).get("mcp_user_id") if request else None
    if user_id is None:
        raise ValueError("MCP authentication required")
    db = SessionLocal()
    started = time.monotonic()
    success = False
    failure = None
    try:
        user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
        if user is None:
            raise HTTPException(status_code=401)
        yield db, user
        success = True
    except Exception as exc:
        db.rollback()
        failure = type(exc).__name__
        logger.warning("MCP tool %s failed (%s)", name, failure)
        safe_message = str(exc) if isinstance(exc, ValueError) else ""
        if safe_message in {"invalid query", "invalid cursor", "invalid direction", "invalid relationship"}:
            raise ValueError(safe_message) from None
        if isinstance(exc, httpx.HTTPStatusError):
            raise ValueError(
                f"upstream service returned HTTP {exc.response.status_code}"
            ) from None
        raise ValueError("MCP request failed or access denied") from None
    finally:
        record_mcp_tool_call(
            db,
            user_id=user_id,
            chat_session_id=None,
            chat_message_id=None,
            project_id=project_id if success else None,
            knowledge_source_id=None,
            server_name="doctus-inbound",
            tool_name=name,
            arguments={**audit_args, "requested_project_id": project_id},
            success=success,
            duration_ms=int((time.monotonic() - started) * 1000),
            error_message=failure,
        )
        db.close()


_api_host = urlsplit(cfg.API_URL).netloc
_hosts = sorted({"localhost:*", "127.0.0.1:*", "[::1]:*", _api_host, *cfg.MCP_ALLOWED_HOSTS})
_origins = sorted({cfg.API_URL, cfg.FRONTEND_URL, *cfg.MCP_ALLOWED_ORIGINS})
mcp = FastMCP(
    "doctus",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
    max_request_body_size=262_144,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[host for host in _hosts if host],
        allowed_origins=[origin for origin in _origins if origin],
    ),
)


@mcp.tool(annotations=READ_ONLY)
def list_visible_projects(ctx: Context, limit: int = 20, offset: int = 0) -> dict:
    """List projects the current Doctus user may open."""
    limit = max(1, min(limit, 50))
    offset = max(0, min(offset, 100_000))
    with _tool_context(ctx, "list_visible_projects", None, {"limit": limit, "offset": offset}) as (db, user):
        page = get_visible_projects_page(user, db, limit + 1, offset)
        return {
            "projects": [
                {"id": item.id, "name": item.name, "is_archived": item.is_archived}
                for item in page[:limit]
            ],
            "next_offset": offset + limit if len(page) > limit else None,
            "limit_applied": limit,
        }


@mcp.tool(annotations=READ_ONLY)
def search_code(ctx: Context, project_id: int, query: str, limit: int = 10) -> dict:
    """Find indexed code entities by symbol, qualified name, or file path in one project.

    Separate alternatives with ``|`` (for example, ``CARDDEMO|AWS CardDemo``).
    """
    query = query.strip()
    limit = max(1, min(limit, 20))
    with _tool_context(ctx, "search_code", project_id, {"limit": limit}) as (db, user):
        if not query or len(query) > 200:
            raise ValueError("invalid query")
        _project(db, user, project_id)
        alternatives = list(dict.fromkeys(part.strip() for part in query.split("|") if part.strip()))
        if len(alternatives) > 12:
            raise ValueError("invalid query")
        hits = []
        seen_ids = set()
        for alternative in alternatives:
            alternative_hits, _ = search_nodes(
                db,
                q=alternative,
                types="entity",
                project_id=project_id,
                limit=limit + 1,
                visible_team_ids=get_visible_team_ids(user, db),
                visible_project_ids=get_visible_project_ids(user, db),
                count_total=False,
            )
            for hit in alternative_hits:
                if hit["node_id"] not in seen_ids:
                    seen_ids.add(hit["node_id"])
                    hits.append(hit)
        visible = []
        for hit in hits:
            try:
                entity = _entity(db, user, project_id, hit["node_id"])
            except HTTPException:
                continue
            visible.append({
                "id": entity.id,
                "project_id": entity.project_id,
                "source_id": entity.source_id,
                "variant_key": entity.variant_key,
                "name": entity.name,
                "qualified_name": entity.qualified_name,
                "type": entity.type,
                "file_path": entity.file_path,
                "start_line": entity.start_line,
                "end_line": entity.end_line,
            })
        return {"results": visible[:limit], "truncated": len(hits) > limit or len(visible) < len(hits), "limit_applied": limit}


@mcp.tool(annotations=READ_ONLY)
def get_code_entity(ctx: Context, project_id: int, entity_id: int) -> dict:
    """Read one indexed code entity and a short original source excerpt."""
    with _tool_context(ctx, "get_code_entity", project_id, {"entity_id": entity_id}) as (db, user):
        _entity(db, user, project_id, entity_id)
        result = entity_api.get_entity(entity_id=entity_id, project_id=project_id, db=db, user=user)
        definition = result.get("definition")
        excerpt, clipped = _bounded(definition.get("content"), 1600) if definition else (None, False)
        return {
            key: result.get(key)
            for key in ("id", "project_id", "source_id", "variant_key", "parent_id", "name", "qualified_name", "type", "file_path", "start_line", "end_line")
        } | {
            "definition": {
                "chunk_id": definition["chunk_id"],
                "start_line": definition["start_line"],
                "end_line": definition["end_line"],
                "content": excerpt,
                "truncated": clipped,
            } if definition else None,
        }


@mcp.tool(annotations=READ_ONLY)
def get_call_flow(ctx: Context, project_id: int, entity_id: int, hops: int = 2, direction: str = "outgoing") -> dict:
    """Trace bounded, indexed calls; unresolved targets and missing evidence stay explicit."""
    hops = max(0, min(hops, 3))
    with _tool_context(ctx, "get_call_flow", project_id, {"entity_id": entity_id, "hops": hops}) as (db, user):
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("invalid direction")
        _entity(db, user, project_id, entity_id)
        result = trace_call_flow(db, project_id=project_id, entity_id=entity_id, hops=hops, direction=direction)
        root_id = (result.get("root") or {}).get("id")
        candidate_nodes = sorted(
            result.get("nodes", []), key=lambda node: (node.get("id") != root_id, node.get("id", 0))
        )[:80]
        source_access = {}
        nodes = []
        for node in candidate_nodes:
            source_id = node.get("source_id")
            if source_id not in source_access:
                source_access[source_id] = _source_visible(db, user, source_id)
            if source_access[source_id]:
                nodes.append(node)
        allowed = {node["id"] for node in nodes}
        edges = [
            {key: edge.get(key) for key in ("id", "source", "target", "target_name", "type", "resolution", "start_line", "end_line")}
            for edge in result.get("edges", [])
            if edge.get("source") in allowed and (edge.get("target") is None or edge.get("target") in allowed)
        ][:120]
        return {
            "project_id": project_id,
            "status": result.get("status"),
            "notice": result.get("notice"),
            "root": result.get("root"),
            "entry_resolution": result.get("entry_resolution"),
            "hops_applied": hops,
            "entry_candidates": result.get("entry_candidates", [])[:20],
            "nodes": nodes,
            "edges": edges,
            "truncated": bool(result.get("truncated") or len(result.get("nodes", [])) > 80 or len(result.get("edges", [])) > 120 or len(result.get("entry_candidates", [])) > 20 or len(nodes) < len(candidate_nodes)),
        }


@mcp.tool(annotations=READ_ONLY)
def get_graph_neighbors(ctx: Context, project_id: int, entity_id: int, relationship: str = "code_dependency", limit: int = 25, cursor: str | None = None) -> dict:
    """Read one relationship class around a code entity; page with next_cursor."""
    limit = max(1, min(limit, 40))
    audited_relationship = relationship if relationship in {"code_dependency", "documented", "manual"} else "invalid"
    with _tool_context(ctx, "get_graph_neighbors", project_id, {"entity_id": entity_id, "limit": limit, "relationship": audited_relationship}) as (db, user):
        if relationship not in {"code_dependency", "documented", "manual"}:
            raise ValueError("invalid relationship")
        if cursor is not None and (not cursor.isdigit() or len(cursor) > 8):
            raise ValueError("invalid cursor")
        _entity(db, user, project_id, entity_id)
        result = graph_api.get_graph_neighborhood(
            node_id=f"entity:{entity_id}",
            project_id=project_id,
            relationships=relationship,
            status="approved",
            direction="both",
            hops=1,
            limit=limit,
            cursor=cursor,
            db=db,
            user=user,
        )
        nodes = []
        source_access = {}
        for node in result.get("nodes", [])[:81]:
            # A document link without a backing chunk has no verifiable project
            # or source scope. Do not expose its title/URL through MCP.
            if node.get("type") == "document" and node.get("project_id") != project_id:
                continue
            if node.get("project_id") not in (None, project_id):
                continue
            source_id = node.get("source_id")
            if source_id not in source_access:
                source_access[source_id] = _source_visible(db, user, source_id)
            if not source_access[source_id]:
                continue
            nodes.append({key: node.get(key) for key in (
                "id", "type", "label", "entity_type", "file_path", "start_line",
                "end_line", "qualified_name", "project_id", "source_id", "url",
                "resource_id", "analysis_status", "analysis_reasons",
            )})
        allowed_ids = {node["id"] for node in nodes}
        edges = [
            {
                **{key: edge.get(key) for key in (
                    "id", "source", "target", "type", "link_type", "relation_type",
                    "direction", "resolution", "chunk_id", "document_file_path",
                    "document_source_id", "document_start_line", "document_end_line",
                    "code_file_path", "code_entity_id", "code_start_line",
                )},
                "references": (edge.get("meta") or {}).get("references", [])[:5],
            }
            for edge in result.get("edges", [])
            if edge.get("source") in allowed_ids and edge.get("target") in allowed_ids
        ]
        edges = edges[:40]
        return {
            "project_id": project_id,
            "relationship": relationship,
            "focus_id": result.get("focus_id"),
            "nodes": nodes,
            "edges": edges,
            "has_more": bool(result.get("has_more")),
            "next_cursor": result.get("next_cursor"),
            "limit_applied": limit,
            "truncated": bool(result.get("has_more") or len(result.get("nodes", [])) > 81 or len(result.get("edges", [])) > 40 or len(nodes) < len(result.get("nodes", [])[:81])),
            "notice": "Only indexed and visible relations are shown; unresolved calls may have no graph target.",
        }


@mcp.tool(annotations=READ_ONLY)
async def search_knowledge(ctx: Context, project_id: int, query: str, limit: int = 5) -> dict:
    """Find short source-backed knowledge excerpts by semantic similarity in one project."""
    query = query.strip()
    limit = max(1, min(limit, 8))
    with _tool_context(ctx, "search_knowledge", project_id, {"limit": limit}) as (db, user):
        if not query or len(query) > 500:
            raise ValueError("invalid query")
        _project(db, user, project_id)
        profile = get_active_embedding_profile(db)
        embedding_config = {
            "embedding_model": profile.model,
            "embedding_provider": profile.provider,
            "embedding_base_url": profile.base_url,
            "embedding_path": profile.path,
            "embedding_api_key": profile.api_key,
            "embedding_dimension": profile.dimension,
            "embedding_context_length": profile.context_length,
        }
        # The embedding request can wait on an external model. Return the DB
        # connection to the pool while it runs, then check current ACLs again.
        db.close()
        chunks = await search_project_chunks(
            db, project_id, query, limit=limit + 1, **embedding_config
        )
        user = db.query(User).filter(User.id == user.id, User.is_active.is_(True)).first()
        if user is None:
            raise HTTPException(status_code=401)
        _project(db, user, project_id)
        results = []
        for chunk in chunks[:limit]:
            if not _source_visible(db, user, chunk.source_id):
                continue
            excerpt, clipped = _bounded(chunk.content, 1200)
            results.append({
                "chunk_id": chunk.id,
                "project_id": project_id,
                "source_id": chunk.source_id,
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content": excerpt,
                "content_truncated": clipped,
            })
        return {"results": results, "truncated": len(chunks) > limit or len(results) < min(len(chunks), limit), "limit_applied": limit, "notice": "Semantic similarity is a retrieval hint, not a verified conclusion."}


class MCPBearerGate:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        if scope.get("path") != "/mcp":
            await PlainTextResponse("Not found", status_code=404)(scope, receive, send)
            return
        auth_headers = [value for key, value in scope.get("headers", []) if key.lower() == b"authorization"]
        auth_parts = auth_headers[0].split(b" ", 1) if len(auth_headers) == 1 else []
        if len(auth_parts) != 2 or auth_parts[0].lower() != b"bearer":
            await PlainTextResponse("Authentication required", status_code=401, headers={"WWW-Authenticate": 'Bearer realm="Doctus MCP"'})(scope, receive, send)
            return
        try:
            secret = auth_parts[1].decode("ascii")
        except UnicodeDecodeError:
            secret = ""
        with SessionLocal() as db:
            user = find_token_user(db, secret)
            user_id = user.id if user else None
        if user_id is None:
            await PlainTextResponse("Authentication required", status_code=401, headers={"WWW-Authenticate": 'Bearer realm="Doctus MCP"'})(scope, receive, send)
            return
        scope.setdefault("state", {})["mcp_user_id"] = user_id

        async def no_store_send(message):
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [*message.get("headers", []), (b"cache-control", b"no-store")],
                }
            await send(message)

        await self.app(scope, receive, no_store_send)


asgi_app = MCPBearerGate(mcp.streamable_http_app())
