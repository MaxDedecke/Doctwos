"""Read-only inbound MCP transport and tools for IDE clients."""

import logging
import re
import time
from contextlib import contextmanager
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from sqlalchemy import func
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
from models.database import CodeEdge, CodeEntity, DocumentChunk, EmbeddingProfile, KnowledgeSource, Project, User
from services.call_flow import trace_call_flow
from services.ai_settings import get_active_embedding_profile
from services.mcp_audit import record_mcp_tool_call
from services.mcp_tokens import find_token_user
from services.ollama_client import search_project_chunks
from services.search import search_nodes


logger = logging.getLogger(__name__)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)


def _search_code_alternatives(query: str) -> list[str]:
    """Normalize symbol alternatives supplied as prose or source declarations."""
    alternatives = []
    seen = set()
    for part in query.split("|"):
        term = re.sub(r"^(?:class|interface|enum|record)\s+", "", part.strip(), flags=re.I)
        if term and term.casefold() not in seen:
            seen.add(term.casefold())
            alternatives.append(term)
    return alternatives


def _research_terms(query: str) -> list[str]:
    """Split explicit symbol lists while keeping ordinary prose intact."""
    explicit = _search_code_alternatives(query)
    if len(explicit) > 1:
        return explicit[:8]
    term = explicit[0] if explicit else ""
    pieces = [part for part in re.split(r"\s+", term) if part]
    if (
        len(pieces) > 1
        and any(any(mark in part for mark in ".#/:()") for part in pieces)
        and all(re.fullmatch(r"[\w$./:#<>(),-]+", part) for part in pieces)
    ):
        return pieces[:8]
    return [term] if term else []


def _symbol_key(value: str | None) -> str:
    value = (value or "").replace("\\", "/").casefold()
    value = value.split("(", 1)[0].replace("#", ".")
    return re.sub(r"\s+", "", value).strip(".")


def _symbol_matches(entity: CodeEntity, term: str) -> bool:
    needle = _symbol_key(term)
    name = _symbol_key(entity.name)
    qualified = _symbol_key(entity.qualified_name)
    path = _symbol_key(entity.file_path)
    if needle in {name, qualified, path}:
        return True
    return bool(needle and (qualified.endswith("." + needle) or path.endswith("/" + needle)))


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


def _entity_analysis(entity: CodeEntity) -> dict:
    meta = entity.meta_json or {}
    keys = (
        "signature", "parameter_types", "return_type", "return_expressions",
        "throws_types", "annotations", "annotation_details", "modifiers", "visibility",
    )
    return {key: meta[key] for key in keys if key in meta}


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


def _knowledge_chunk_in_project(
    db: Session, user: User, project_id: int, chunk: DocumentChunk
) -> bool:
    """Require both the requested project scope and its optional source ACL."""
    if chunk.project_id not in (None, project_id):
        return False
    if chunk.source_id is None:
        # Source-less Git chunks belong to a project directly. Unscoped legacy
        # chunks must not become visible just because they have no source ACL.
        return chunk.project_id == project_id
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == chunk.source_id).first()
    if source is None or source.project_id != project_id:
        return False
    try:
        assert_knowledge_source_visible(source, user, db)
    except HTTPException:
        return False
    return True


def _embedding_profile_for_project(db: Session, project_id: int):
    """Use the unique embedding profile matching a project's indexed vectors.

    The active profile is deployment-wide, while projects may have been
    indexed with different models. Prefer an unambiguous project model so an
    MCP query is embedded in the same vector space as its chunks. For legacy
    projects with multiple models or multiple profiles for the same model,
    retain the active-profile behavior.
    """
    source_models = {
        model
        for (model,) in db.query(KnowledgeSource.embedding_model)
        .filter(KnowledgeSource.project_id == project_id)
        .distinct()
        .all()
        if model
    }
    chunk_models = {
        model
        for (model,) in db.query(DocumentChunk.embedding_model)
        .filter(DocumentChunk.project_id == project_id)
        .distinct()
        .all()
        if model
    }
    models = source_models or chunk_models
    if len(models) == 1:
        model = next(iter(models))
        profiles = db.query(EmbeddingProfile).filter(EmbeddingProfile.model == model).all()
        if len(profiles) == 1:
            return profiles[0]
    return get_active_embedding_profile(db)


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
        if safe_message in {"invalid query", "invalid cursor", "invalid direction", "invalid relationship", "invalid scope"}:
            # Keep validation errors useful to MCP clients without exposing
            # database or authorization details.
            raise ValueError(safe_message) from None
        if isinstance(exc, httpx.HTTPStatusError):
            upstream = "embedding endpoint" if name == "search_knowledge" else "upstream service"
            detail = f"{upstream} returned HTTP {exc.response.status_code}"
            if name == "search_knowledge" and exc.response.status_code == 404:
                detail += "; check the active embedding profile URL and path"
            raise ValueError(detail) from None
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
def search_code(
    ctx: Context,
    project_id: int,
    query: str,
    limit: int = 10,
    include_source: bool = True,
) -> dict:
    """Find indexed code entities by symbol, qualified name, or file path in one project.

    Separate alternatives with ``|``. Optional declaration prefixes such as
    ``class`` are ignored (for example, ``class ConnectorLogic|class Other``).
    Use ``get_code_entity`` to page the original declaration, and
    ``trace_data_access`` when a returned entity is a data item or routine.
    """
    query = query.strip()
    limit = max(1, min(limit, 20))
    with _tool_context(ctx, "search_code", project_id, {"limit": limit, "include_source": include_source}) as (db, user):
        if not query or len(query) > 200:
            raise ValueError("invalid query")
        _project(db, user, project_id)
        alternatives = _search_code_alternatives(query)
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
        for hit in hits[:limit]:
            try:
                entity = _entity(db, user, project_id, hit["node_id"])
            except HTTPException:
                continue
            item = {
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
                "analysis": _entity_analysis(entity),
            }
            # Give the best few symbol matches enough original source to cite
            # without making every result a full-file response.
            if include_source and len(visible) < 3:
                result = entity_api.get_entity(
                    entity_id=entity.id, project_id=project_id, db=db, user=user
                )
                definition = result.get("definition")
                if definition:
                    excerpt, clipped = _bounded(definition.get("content"), 1600)
                    item["source_excerpt"] = {
                        "start_line": definition["start_line"],
                        "end_line": definition["end_line"],
                        "source_ranges": definition.get("source_ranges", []),
                        "delivered_start_line": definition["start_line"],
                        "delivered_end_line": min(
                            definition["end_line"],
                            definition["start_line"] + max(
                                0,
                                len((excerpt or "").splitlines()) - 1,
                            ),
                        ),
                        "content": excerpt,
                        "truncated": clipped,
                        "next_start_line": definition.get("next_start_line"),
                        "next_chunk_id": definition["chunk_id"] if clipped else definition.get("next_chunk_id"),
                        "next_char_offset": len(excerpt or "") if clipped else 0,
                    }
            visible.append(item)
        follow_up_actions = []
        for item in visible[:3]:
            follow_up_actions.append({
                "tool": "get_code_entity",
                "arguments": {"project_id": project_id, "entity_id": item["id"], "max_chars": 5000},
                "reason": "Read the source ranges and continue with the returned chunk cursor.",
            })
            if item["type"] in {"data_item", "sql_table", "file_fd", "record"}:
                follow_up_actions.append({
                    "tool": "trace_data_access",
                    "arguments": {"project_id": project_id, "entity_id": item["id"], "limit": 12},
                    "reason": "Inspect indexed reads and writes for this data entity.",
                })
        return {
            "results": visible[:limit],
            "truncated": len(hits) > limit or len(visible) < len(hits),
            "limit_applied": limit,
            "follow_up_actions": follow_up_actions[:6],
        }


@mcp.tool(annotations=READ_ONLY)
def research_project(ctx: Context, project_id: int, query: str, limit: int = 8, hops: int = 2) -> dict:
    """Search symbols and, for one exact candidate, resolve its bounded call flow."""
    query = query.strip()
    limit = max(1, min(limit, 12))
    hops = max(0, min(hops, 3))
    with _tool_context(ctx, "research_project", project_id, {"limit": limit, "hops": hops}) as (db, user):
        if not query or len(query) > 200:
            raise ValueError("invalid query")
        _project(db, user, project_id)
        terms = _research_terms(query)
        by_id: dict[int, CodeEntity] = {}
        visible_teams = get_visible_team_ids(user, db)
        visible_projects = get_visible_project_ids(user, db)
        for term in terms:
            hits, _ = search_nodes(
                db, q=term, types="entity", project_id=project_id, limit=limit + 1,
                visible_team_ids=visible_teams, visible_project_ids=visible_projects,
                count_total=False,
            )
            needle = term.replace("\\", "/").casefold()
            if "/" in needle:
                exact_files = db.query(CodeEntity).filter(
                    CodeEntity.project_id == project_id,
                    func.lower(CodeEntity.file_path) == needle,
                ).order_by(CodeEntity.start_line, CodeEntity.id).limit(limit + 1).all()
                for entity in exact_files:
                    try:
                        by_id[entity.id] = _entity(db, user, project_id, entity.id)
                    except HTTPException:
                        continue
            for hit in hits:
                try:
                    entity = _entity(db, user, project_id, hit["node_id"])
                except HTTPException:
                    continue
                by_id[entity.id] = entity

        def serialize(entity: CodeEntity) -> dict:
            return {
                "id": entity.id, "project_id": entity.project_id, "source_id": entity.source_id,
                "variant_key": entity.variant_key, "name": entity.name,
                "qualified_name": entity.qualified_name, "type": entity.type,
                "file_path": entity.file_path, "start_line": entity.start_line,
                "end_line": entity.end_line,
                "analysis": _entity_analysis(entity),
            }

        candidates = [serialize(entity) for entity in by_id.values()]
        matches = []
        for term in terms:
            exact = [serialize(entity) for entity in by_id.values() if _symbol_matches(entity, term)]
            if "/" in term:
                file_programs = [item for item in exact if item["type"] in {"program", "cobol_program", "compilation_unit"}]
                if file_programs:
                    exact = file_programs
            match = {
                "query": term,
                "resolution": "unique_exact_match" if len(exact) == 1 else (
                    "ambiguous" if len(exact) > 1 else "no_exact_match"
                ),
                "candidates": exact[:limit],
                "candidate_count": len(exact),
            }
            if len(exact) == 1:
                match["call_flow"] = trace_call_flow(
                    db, project_id=project_id, entity_id=exact[0]["id"],
                    hops=hops, direction="outgoing", scope="execution",
                )
                match["follow_up_actions"] = [{
                    "tool": "get_code_entity",
                    "arguments": {"project_id": project_id, "entity_id": exact[0]["id"], "max_chars": 5000},
                    "reason": "Read the indexed declaration and its original source chunks.",
                }]
            elif not exact:
                match["follow_up_actions"] = [{
                    "tool": "search_knowledge",
                    "arguments": {"project_id": project_id, "query": term, "limit": 5},
                    "reason": "The symbol search found no exact indexed entity; check project knowledge for a domain-level answer.",
                }]
            matches.append(match)

        if len(matches) == 1:
            match = matches[0]
            return {
                "project_id": project_id, "query": query,
                "candidates": candidates[:limit], "candidate_count": len(candidates),
                "candidates_truncated": len(candidates) > limit,
                **match,
            }
        return {
            "project_id": project_id, "query": query,
            "resolution": "multiple_queries", "matches": matches,
            "candidates": candidates[:limit], "candidate_count": len(candidates),
            "candidates_truncated": len(candidates) > limit,
            "notice": "Jedes explizite Symbol wurde getrennt aufgelöst; Mehrdeutigkeit bleibt pro Symbol sichtbar.",
        }


@mcp.tool(annotations=READ_ONLY)
def get_code_entity(
    ctx: Context,
    project_id: int,
    entity_id: int,
    start_line: int | None = None,
    end_line: int | None = None,
    max_chars: int = 5000,
    chunk_id: int | None = None,
    char_offset: int = 0,
) -> dict:
    """Read an indexed entity with paged, line-attributed original source."""
    max_chars = max(500, min(max_chars, 5000))
    if start_line is not None and start_line < 1:
        raise ValueError("invalid start_line")
    if end_line is not None and (end_line < 1 or (start_line is not None and end_line < start_line)):
        raise ValueError("invalid end_line")
    if char_offset < 0 or char_offset > 1_000_000:
        raise ValueError("invalid char_offset")
    with _tool_context(ctx, "get_code_entity", project_id, {
        "entity_id": entity_id, "start_line": start_line, "end_line": end_line,
        "max_chars": max_chars, "chunk_id": chunk_id, "char_offset": char_offset,
    }) as (db, user):
        entity = _entity(db, user, project_id, entity_id)
        if chunk_id is None:
            source_chunks = entity_api._definition_chunks(
                entity, db, start_line=start_line, end_line=end_line
            )
        else:
            source_chunks = db.query(DocumentChunk).filter(
                DocumentChunk.id == chunk_id,
                DocumentChunk.project_id == entity.project_id,
                DocumentChunk.source_id == entity.source_id,
                DocumentChunk.file_path == entity.file_path,
            ).all()
        sections = []
        remaining = max_chars
        next_chunk_id = None
        next_char_offset = 0
        for index, chunk in enumerate(source_chunks):
            offset = char_offset if index == 0 and chunk_id is not None else 0
            content = chunk.content[offset:offset + remaining]
            clipped = offset + len(content) < len(chunk.content)
            delivered_start = chunk.start_line + chunk.content[:offset].count("\n")
            delivered_line_count = content.count("\n") + int(bool(content) and not content.endswith("\n"))
            delivered_end = min(chunk.end_line, delivered_start + max(0, delivered_line_count - 1))
            sections.append({
                "chunk_id": chunk.id,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "delivered_start_line": delivered_start,
                "delivered_end_line": delivered_end,
                "content": content,
                "truncated": clipped,
            })
            remaining -= len(content)
            if clipped:
                next_chunk_id = chunk.id
                next_char_offset = offset + len(content)
                break
            if remaining <= 0 and index + 1 < len(source_chunks):
                next_chunk_id = source_chunks[index + 1].id
                next_char_offset = 0
                break

        has_more = next_chunk_id is not None
        return {
            "id": entity.id,
            "project_id": entity.project_id,
            "source_id": entity.source_id,
            "variant_key": entity.variant_key,
            "parent_id": entity.parent_id,
            "name": entity.name,
            "qualified_name": entity.qualified_name,
            "type": entity.type,
            "file_path": entity.file_path,
            "start_line": entity.start_line,
            "end_line": entity.end_line,
            "analysis": _entity_analysis(entity),
            "definition": {
                "sections": sections,
                "truncated": has_more,
                "next_chunk_id": next_chunk_id,
                "next_char_offset": next_char_offset if has_more else None,
                "notice": "Jede Quellspanne bezieht sich auf den Originalchunk; weiter mit next_chunk_id/next_char_offset abrufen.",
                "follow_up_actions": [{
                    "tool": "get_code_entity",
                    "arguments": {
                        "project_id": project_id,
                        "entity_id": entity.id,
                        "chunk_id": next_chunk_id,
                        "char_offset": next_char_offset,
                        "max_chars": max_chars,
                    },
                    "reason": "Continue reading the remaining indexed source segment.",
                }] if has_more else [],
            } if sections else None,
        }


@mcp.tool(annotations=READ_ONLY)
def trace_data_access(ctx: Context, project_id: int, entity_id: int, limit: int = 12) -> dict:
    """List indexed READS/WRITES for a data entity or routine with source evidence.

    Results are ordered by source line. They describe indexed references, not
    a complete path-sensitive runtime data flow; a missing edge is not proof
    that the source never accesses the data.
    """
    limit = max(1, min(limit, 20))
    with _tool_context(ctx, "trace_data_access", project_id, {"entity_id": entity_id, "limit": limit}) as (db, user):
        entity = _entity(db, user, project_id, entity_id)
        access_query = db.query(CodeEdge).filter(
            CodeEdge.project_id == project_id,
            CodeEdge.type.in_(["READS", "WRITES"]),
        )
        if entity.type in {"data_item", "sql_table", "file_fd", "record"}:
            access_query = access_query.filter(CodeEdge.dst_entity_id == entity_id)
        else:
            access_query = access_query.filter(CodeEdge.src_entity_id == entity_id)
        rows = access_query.order_by(CodeEdge.src_start_line, CodeEdge.id).limit(limit + 1).all()
        accesses = []
        for edge in rows[:limit]:
            routine_id = edge.src_entity_id
            routine = db.query(CodeEntity).filter(
                CodeEntity.id == routine_id, CodeEntity.project_id == project_id
            ).first()
            if routine is None or not _source_visible(db, user, routine.source_id):
                continue
            line = edge.src_start_line
            chunk_query = db.query(DocumentChunk).filter(
                DocumentChunk.project_id == project_id,
                DocumentChunk.source_id == routine.source_id,
                DocumentChunk.file_path == routine.file_path,
            )
            if line is not None:
                chunk_query = chunk_query.filter(
                    DocumentChunk.start_line <= line,
                    DocumentChunk.end_line >= line,
                )
            chunk = chunk_query.order_by(DocumentChunk.start_line, DocumentChunk.id).first()
            excerpt = None
            if chunk is not None:
                content, clipped = _bounded(chunk.content, 1200)
                excerpt = {
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": content,
                    "truncated": clipped,
                }
            meta = edge.meta_json or {}
            accesses.append({
                "edge_id": edge.id,
                "access": edge.type,
                "resolution": edge.resolution,
                "operation": meta.get("operation"),
                "operand_role": meta.get("operand_role"),
                "control_context": meta.get("control_context"),
                "line": line,
                "end_line": edge.src_end_line,
                "routine": {
                    "id": routine.id,
                    "name": routine.name,
                    "qualified_name": routine.qualified_name,
                    "file_path": routine.file_path,
                },
                "target_name": edge.dst_name,
                "target_qualified_name": meta.get("target_qualified_name"),
                "source_excerpt": excerpt,
            })
        truncated = len(rows) > limit or len(accesses) < min(len(rows), limit)
        return {
            "project_id": project_id,
            "entity": {"id": entity.id, "name": entity.name, "type": entity.type},
            "accesses": accesses,
            "accesses_returned": len(accesses),
            "truncated": truncated,
            "notice": "Indexierte READS/WRITES in Quellreihenfolge; kein vollständiger Kontrollfluss- oder Laufzeitbeweis.",
        }


@mcp.tool(annotations=READ_ONLY)
def get_call_flow(
    ctx: Context,
    project_id: int,
    entity_id: int,
    hops: int = 2,
    direction: Literal["outgoing", "incoming", "both"] = "outgoing",
    scope: Literal["execution", "dependencies", "all"] = "execution",
) -> dict:
    """Trace executable calls or resource/data dependencies in a project.

    ``scope`` selects ``execution`` (CALL/PERFORM/etc.), ``dependencies``
    (COPY/import/resource/data edges), or ``all``. ``direction`` is outgoing,
    incoming, or both.
    """
    hops = max(0, min(hops, 3))
    with _tool_context(ctx, "get_call_flow", project_id, {"entity_id": entity_id, "hops": hops, "scope": scope}) as (db, user):
        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError("invalid direction")
        if scope not in {"execution", "dependencies", "all"}:
            raise ValueError("invalid scope")
        _entity(db, user, project_id, entity_id)
        result = trace_call_flow(db, project_id=project_id, entity_id=entity_id, hops=hops, direction=direction, scope=scope)
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
            {
                **{
                    key: edge.get(key)
                    for key in ("id", "source", "target", "target_name", "type", "resolution", "start_line", "end_line")
                },
                "resolution_evidence": {
                    key: (edge.get("meta") or {})[key]
                    for key in (
                        "target_qualified_name",
                        "target_file_path",
                        "resolution_reason",
                        "resolution_scope",
                        "receiver",
                        "receiver_resolution",
                        "receiver_symbol_qualified_name",
                        "receiver_type_qualified_name",
                        "receiver_method_qualified_name",
                        "argument_count",
                        "argument_types",
                        "argument_expressions",
                        "control_role",
                        "control_context",
                        "exception_types",
                        "dispatch_scope",
                    )
                    if key in (edge.get("meta") or {})
                },
            }
            for edge in result.get("edges", [])
            if edge.get("source") in allowed and (edge.get("target") is None or edge.get("target") in allowed)
        ][:120]
        truncated = bool(
            result.get("truncated")
            or len(result.get("nodes", [])) > 80
            or len(result.get("edges", [])) > 120
            or len(result.get("entry_candidates", [])) > 20
            or len(nodes) < len(candidate_nodes)
        )
        return {
            "project_id": project_id,
            "status": result.get("status"),
            "notice": result.get("notice"),
            "root": result.get("root"),
            "entry_resolution": result.get("entry_resolution"),
            "hops_applied": hops,
            "scope": scope,
            "entry_candidates": result.get("entry_candidates", [])[:20],
            "nodes": nodes,
            "edges": edges,
            "truncated": truncated,
            "truncation": {
                "reason": "node_or_edge_limit_or_source_visibility" if truncated else None,
                "nodes_returned": len(nodes),
                "nodes_available": len(result.get("nodes", [])),
                "nodes_omitted": max(0, len(result.get("nodes", [])) - len(nodes)),
                "edges_returned": len(edges),
                "edges_available": len(result.get("edges", [])),
                "edges_omitted": max(0, len(result.get("edges", [])) - len(edges)),
                "next_cursor": None,
            },
            "follow_up_hint": (
                "Erneut am ausgegebenen root.id abfragen und scope (execution/dependencies/all), "
                "direction oder hops eingrenzen; dieser Call-Flow hat keinen Seiten-Cursor."
                if truncated else None
            ),
        }


@mcp.tool(annotations=READ_ONLY)
def get_graph_neighbors(
    ctx: Context,
    project_id: int,
    entity_id: int,
    relationship: Literal["code_dependency", "documented", "manual"] = "code_dependency",
    limit: int = 25,
    cursor: str | None = None,
) -> dict:
    """Read one graph relationship class around an entity and page with next_cursor.

    ``relationship`` selects ``code_dependency``, ``documented``, or ``manual``;
    call-graph edge types such as ``PERFORM`` are not relationship filters.
    """
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
        truncated = bool(result.get("has_more") or len(result.get("nodes", [])) > 81
                         or len(result.get("edges", [])) > 40
                         or len(nodes) < len(result.get("nodes", [])[:81]))
        return {
            "project_id": project_id,
            "relationship": relationship,
            "focus_id": result.get("focus_id"),
            "nodes": nodes,
            "edges": edges,
            "has_more": bool(result.get("has_more")),
            "next_cursor": result.get("next_cursor"),
            "limit_applied": limit,
            "truncated": truncated,
            "truncation": {
                "reason": "relationship_page_has_more" if result.get("has_more") else (
                    "response_limit_or_source_visibility" if truncated else None
                ),
                "nodes_returned": len(nodes),
                "nodes_available": len(result.get("nodes", [])),
                "nodes_omitted": max(0, len(result.get("nodes", [])) - len(nodes)),
                "edges_returned": len(edges),
                "edges_available": len(result.get("edges", [])),
                "edges_omitted": max(0, len(result.get("edges", [])) - len(edges)),
                "next_cursor": result.get("next_cursor") if result.get("has_more") else None,
            },
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
        profile = _embedding_profile_for_project(db, project_id)
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
            if not _knowledge_chunk_in_project(db, user, project_id, chunk):
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
