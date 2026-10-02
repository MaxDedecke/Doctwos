"""Read-only inbound MCP transport and tools for IDE clients."""

from contextlib import asynccontextmanager
import logging
import base64
import binascii
import hashlib
import json
import re
import time
from contextlib import contextmanager
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from sqlalchemy import and_, func, or_
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
from services.call_flow import (
    CALL_FLOW_MAX_EDGES,
    CALL_FLOW_MAX_NODES,
    trace_call_flow,
)
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

    def symbol_like(part: str) -> bool:
        # Prose such as "approval/decline" or "how" must not be split into symbols.
        if not re.fullmatch(r"[\w$./:#<>(),-]+", part):
            return False
        return bool(
            any(mark in part for mark in ".#:()_$")
            or re.search(r"[a-z][A-Z]", part)
            or re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", part)
        )

    if len(pieces) > 1 and all(symbol_like(part) for part in pieces):
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


_DOTTED = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+$")
_STOPWORDS = {"wie", "was", "der", "die", "das", "und", "oder", "the", "and", "how", "does", "what", "for", "with", "von", "mit"}
_STRUCTURAL = {"program", "cobol_program", "section", "paragraph", "class", "interface", "enum", "record", "method", "constructor"}
_TYPE_RANK = {"method": 0, "paragraph": 0, "constructor": 1, "program": 0, "cobol_program": 0, "section": 1, "class": 1,
              "interface": 1, "enum": 1, "record": 1, "field": 2, "data_item": 2, "compilation_unit": 3}


def _query_variants(term: str) -> list[str]:
    """Spellings an index may use for one symbol: Java methods are stored as ``Klasse#methode``."""
    term = term.strip()
    base = term.split("(", 1)[0]
    variants = [term]
    if _DOTTED.match(base):
        parts = base.split(".")
        variants.append(".".join(parts[:-1]) + "#" + parts[-1])
        if len(parts) > 2:
            variants.append(parts[-2] + "#" + parts[-1])
            variants.append(parts[-2] + "." + parts[-1])
    out, seen = [], set()
    for variant in variants:
        if variant.casefold() not in seen:
            seen.add(variant.casefold())
            out.append(variant)
    return out


def _symbol_like(token: str) -> bool:
    return bool(any(mark in token for mark in ".#:()_$") or re.search(r"[a-z][A-Z]", token)
                or re.fullmatch(r"[A-Z0-9]+(?:-[A-Z0-9]+)+", token))


def _entity_haystack(entity: CodeEntity) -> str:
    return " ".join([entity.name or "", (entity.qualified_name or "").replace("#", "."), entity.file_path or ""]).casefold()


def _find_entities(db: Session, user: User, project_id: int, term: str, limit: int) -> tuple[list[CodeEntity], list[dict], str]:
    """Tolerant symbol lookup: spelling variants, multi-word fallback, suggestions when nothing matches.

    Returns ``(entities, suggestions, mode)``; ``mode`` is ``exact``, ``tokens`` or ``none``.
    Exact symbol matches are listed first, then structural entities before fields.
    """
    visible_teams = get_visible_team_ids(user, db)
    visible_projects = get_visible_project_ids(user, db)

    def search(query: str, size: int) -> list[CodeEntity]:
        hits, _ = search_nodes(
            db, q=query, types="entity", project_id=project_id, limit=size,
            visible_team_ids=visible_teams, visible_project_ids=visible_projects, count_total=False,
        )
        found = []
        for hit in hits:
            try:
                found.append(_entity(db, user, project_id, hit["node_id"]))
            except HTTPException:
                continue
        return found

    found: list[CodeEntity] = []
    seen: set[int] = set()
    mode = "exact"
    for variant in _query_variants(term):
        for entity in search(variant, limit + 1):
            if entity.id not in seen:
                seen.add(entity.id)
                found.append(entity)
        if any(_symbol_matches(entity, variant) for entity in found):
            break
    if not found:
        tokens = [t for t in re.split(r"[\s,;|]+", term.strip()) if len(t) >= 3 and t.casefold() not in _STOPWORDS]
        if len(tokens) > 1:
            mode = "tokens"
            anchor = max(tokens, key=lambda t: (_symbol_like(t), len(t)))
            rest = [t.casefold() for t in tokens if t != anchor]
            pool: dict[int, CodeEntity] = {}
            for variant in _query_variants(anchor):
                for entity in search(variant, 80):
                    pool[entity.id] = entity
            scored = sorted(((sum(t in _entity_haystack(e) for t in rest), e) for e in pool.values()), key=lambda x: -x[0])
            found = [e for score, e in scored if score == len(rest)] or [e for score, e in scored if score > 0]
            found = found[: limit + 1]
    suggestions: list[dict] = []
    if not found:
        mode = "none"
        for head in [t for t in re.split(r"[.#\s(|]+", term) if len(t) >= 3][:2]:
            for entity in search(head, 5):
                suggestions.append({"qualified_name": entity.qualified_name, "type": entity.type,
                                    "file_path": entity.file_path, "start_line": entity.start_line})
            if suggestions:
                break
    found.sort(key=lambda e: (0 if _symbol_matches(e, term) else 1, _TYPE_RANK.get(e.type, 4), e.file_path or "", e.start_line or 0))
    return found, suggestions[:5], mode


def _compact_entity(entity: CodeEntity) -> dict:
    meta = entity.meta_json or {}
    item = {
        "id": entity.id, "qualified_name": entity.qualified_name, "type": entity.type,
        "file_path": entity.file_path, "start_line": entity.start_line, "end_line": entity.end_line,
    }
    if meta.get("signature"):
        item["signature"] = meta["signature"]
    return item


def _numbered(text: str, start_line: int) -> str:
    return "\n".join(f"{start_line + i}: {line}" for i, line in enumerate(text.splitlines()))


class ToolInputError(ValueError):
    """Input problem whose message is safe to show: it only names symbols the caller may already see."""


def _pick_entity(structural: list[CodeEntity]) -> tuple[CodeEntity | None, list[CodeEntity]]:
    """Choose one entity among exact matches or return (None, candidates) when it stays ambiguous.

    Overloads in one file: first by line. Otherwise prefer non-test paths, then one declaring type/program.
    """
    if len(structural) == 1:
        return structural[0], []
    pool = structural
    if len({e.file_path for e in pool}) > 1:
        non_test = [e for e in pool if "/test/" not in (e.file_path or "")]
        pool = non_test or pool
    if len({e.file_path for e in pool}) > 1:
        declaring = [e for e in pool if e.type in {"class", "interface", "enum", "record", "program", "cobol_program"}]
        pool = declaring or pool
    if len({e.file_path for e in pool}) > 1:
        return None, structural
    pool = sorted(pool, key=lambda e: (_TYPE_RANK.get(e.type, 4), e.start_line or 0))
    return pool[0], [e for e in structural if e is not pool[0]]


def _resolve_symbol(db: Session, user: User, project_id: int, symbol: str) -> CodeEntity:
    """One entity for a symbol name, or a ValueError that names the candidates."""
    found, suggestions, _ = _find_entities(db, user, project_id, symbol, 8)
    exact = [e for e in found if _symbol_matches(e, symbol)] or found
    structural = [e for e in exact if e.type in _STRUCTURAL] or exact
    if not structural:
        hint = "; ".join(str(s["qualified_name"]) for s in suggestions) or "none"
        raise ToolInputError(f"symbol not found: {symbol}. Similar: {hint}")
    picked, _ = _pick_entity(structural)
    if picked is not None:
        return picked
    names = "; ".join(f"{e.qualified_name} ({e.file_path}:{e.start_line})" for e in structural[:6])
    raise ToolInputError(f"symbol is ambiguous: {symbol}. Use one qualified name: {names}")


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
        "throws_types", "exception_flow", "annotations", "annotation_details", "modifiers", "visibility",
    )
    return {key: meta[key] for key in keys if key in meta}


def _capture_mcp_result(ctx: Context, db: Session, project_id: int | None, result: dict) -> None:
    """Attach content-free result telemetry to this call's audit record."""
    request = ctx.request_context.request
    if request is None:
        return

    def has_truncation(value) -> bool:
        if isinstance(value, dict):
            return any(
                (key in {"truncated", "has_more", "continuation_limit_reached"} and item is True)
                or has_truncation(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(has_truncation(item) for item in value)
        return False

    try:
        payload_bytes = len(json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str).encode())
        revision = None
        if project_id is not None:
            variants = [
                row[0]
                for row in db.query(CodeEntity.variant_key)
                .filter(CodeEntity.project_id == project_id)
                .distinct()
                .order_by(CodeEntity.variant_key)
                .limit(1000)
                .all()
            ]
            revision = f"{len(variants)}:{hashlib.sha256('|'.join(variants).encode()).hexdigest()[:16]}"
        request.scope.setdefault("state", {})["doctus_mcp_result_metrics"] = {
            "result_payload_bytes": payload_bytes,
            "result_truncated": has_truncation(result),
            "index_revision": revision,
        }
    except Exception:
        logger.debug("Unable to capture MCP result metrics", exc_info=True)


def _flow_edge_excerpt(
    db: Session,
    project_id: int,
    source_node: dict,
    edge: dict,
    char_budget: int,
) -> dict | None:
    focus_line = edge.get("start_line")
    if not isinstance(focus_line, int) or focus_line < 1:
        return None
    query = db.query(DocumentChunk).filter(
        DocumentChunk.project_id == project_id,
        DocumentChunk.source_id == source_node.get("source_id"),
        DocumentChunk.file_path == source_node.get("file_path"),
        DocumentChunk.start_line <= focus_line,
        DocumentChunk.end_line >= focus_line,
    )
    chunk = query.order_by(DocumentChunk.start_line, DocumentChunk.id).first()
    if chunk is None:
        return None
    lines = chunk.content.splitlines(keepends=True)
    if not lines:
        return None
    focus_index = max(0, min(len(lines) - 1, focus_line - chunk.start_line))
    first_index = max(0, focus_index - 5)
    last_index = min(len(lines), focus_index + 9)
    prefix_chars = sum(len(value) for value in lines[:first_index])
    excerpt = "".join(lines[first_index:last_index])
    content = excerpt[:char_budget]
    delivered_start = chunk.start_line + first_index
    delivered_lines = content.count("\n") + int(bool(content) and not content.endswith("\n"))
    delivered_end = min(chunk.end_line, delivered_start + max(0, delivered_lines - 1))
    truncated = len(content) < len(excerpt)
    return {
        "chunk_id": chunk.id,
        "focus_line": focus_line,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "delivered_start_line": delivered_start,
        "delivered_end_line": delivered_end,
        "content": content,
        "truncated": truncated,
        "follow_up_action": {
            "tool": "get_code_entity",
            "arguments": {
                "project_id": project_id,
                "entity_id": edge.get("source"),
                "chunk_id": chunk.id,
                "char_offset": prefix_chars + len(content) if truncated else 0,
                "max_chars": 5000,
            },
            "reason": "Read the original indexed chunk around this call site.",
        },
    }


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


def _lexical_project_chunks(db: Session, project_id: int, query: str, limit: int) -> list[DocumentChunk]:
    """Keyword fallback for search_knowledge when the embedding endpoint is unusable."""
    terms = list(dict.fromkeys(t.lower() for t in re.findall(r"\w{3,}", query)))[:6]
    if not terms:
        return []
    source_ids = [row.id for row in db.query(KnowledgeSource.id).filter(KnowledgeSource.project_id == project_id)]
    scope = DocumentChunk.project_id == project_id
    if source_ids:
        scope = or_(scope, and_(DocumentChunk.project_id.is_(None), DocumentChunk.source_id.in_(source_ids)))
    # Chunk content is stored encrypted, so SQL cannot match it: scan a bounded,
    # project-scoped window in Python. This is only the degraded fallback path.
    def hits(chunk: DocumentChunk) -> int:
        haystack = f"{chunk.file_path or ''}\n{chunk.content or ''}".lower()
        return sum(t in haystack for t in terms)

    candidates = db.query(DocumentChunk).filter(scope).order_by(DocumentChunk.id).limit(3000).all()
    scored = sorted(
        ((hits(c), c) for c in candidates), key=lambda pair: (-pair[0], pair[1].id)
    )
    scored = [c for score, c in scored if score]
    return scored[:limit]


@contextmanager
def _tool_context(ctx: Context, name: str, project_id: int | None, audit_args: dict):
    request = ctx.request_context.request
    state = request.scope.setdefault("state", {}) if request else {}
    state.pop("doctus_mcp_result_metrics", None)
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
        if isinstance(exc, ToolInputError):
            raise ValueError(safe_message) from None
        if safe_message in {
            "invalid query", "invalid cursor", "invalid direction", "invalid relationship",
            "invalid scope", "cursor does not match this call-flow query",
        }:
            # Keep validation errors useful to MCP clients without exposing
            # database or authorization details.
            if "cursor" in safe_message:
                safe_message += (
                    ". Retry with the next_cursor string copied unchanged from the previous "
                    "response, or omit cursor to restart from the first page."
                )
            raise ValueError(safe_message) from None
        if isinstance(exc, httpx.HTTPStatusError):
            upstream = "embedding endpoint" if name == "search_knowledge" else "upstream service"
            detail = f"{upstream} returned HTTP {exc.response.status_code}"
            if name == "search_knowledge" and exc.response.status_code == 404:
                detail += "; check the active embedding profile URL and path"
            raise ValueError(detail) from None
        raise ValueError("MCP request failed or access denied") from None
    finally:
        result_metrics = state.pop("doctus_mcp_result_metrics", {})
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
            **result_metrics,
            error_message=failure,
        )
        db.close()


_api_host = urlsplit(cfg.API_URL).netloc
_hosts = sorted({"localhost:*", "127.0.0.1:*", "[::1]:*", _api_host, *cfg.MCP_ALLOWED_HOSTS})
_origins = sorted({cfg.API_URL, cfg.FRONTEND_URL, *cfg.MCP_ALLOWED_ORIGINS})
mcp = FastMCP(
    "doctus",
    instructions=(
        "Doctus indexes source code. For any named class, method, program or paragraph call explain_symbol first: "
        "it returns the original source with line numbers, callers, callees and data access in one call "
        "(a large program or class returns an outline; call explain_symbol again with one outline symbol). "
        "Use search_code only to discover names, search_knowledge for wording or business terms. "
        "Cite the file:line numbers from the results."
    ),
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
    detail: Annotated[str, Field(description="'compact' (default): one line per hit, source only for the best exact match. 'full': three source excerpts and analysis blobs.")] = "compact",
) -> dict:
    """Find indexed code entities by symbol, qualified name, or file path in one project.

    Accepts ``Klasse.methode`` and ``Klasse#methode`` alike, several alternatives separated by ``|``,
    and short phrases such as ``authenticate AuthDataAccessor``. An empty result lists similar names.
    To understand a symbol use ``explain_symbol`` (source, callers, callees and data access in one call).
    """
    query = query.strip()
    limit = max(1, min(limit, 20))
    if detail not in {"compact", "full"}:
        raise ValueError("invalid detail")
    with _tool_context(ctx, "search_code", project_id, {"limit": limit, "include_source": include_source, "detail": detail}) as (db, user):
        if not query or len(query) > 200:
            raise ValueError("invalid query")
        _project(db, user, project_id)
        alternatives = _search_code_alternatives(query)
        if len(alternatives) > 12:
            raise ValueError("invalid query")
        entities: list[CodeEntity] = []
        seen_ids: set[int] = set()
        suggestions: list[dict] = []
        modes = []
        for alternative in alternatives:
            found, alt_suggestions, mode = _find_entities(db, user, project_id, alternative, limit)
            modes.append(mode)
            suggestions += alt_suggestions
            for entity in found:
                if entity.id not in seen_ids:
                    seen_ids.add(entity.id)
                    entities.append(entity)
        total = len(entities)
        entities = entities[:limit]
        compact = detail == "compact"
        visible = []
        for entity in entities:
            if compact:
                item = _compact_entity(entity)
                item.update({"project_id": entity.project_id, "source_id": entity.source_id, "variant_key": entity.variant_key, "name": entity.name})
            else:
                item = {
                    "id": entity.id, "project_id": entity.project_id, "source_id": entity.source_id,
                    "variant_key": entity.variant_key, "name": entity.name, "qualified_name": entity.qualified_name,
                    "type": entity.type, "file_path": entity.file_path, "start_line": entity.start_line,
                    "end_line": entity.end_line, "analysis": _entity_analysis(entity),
                }
            exact = any(_symbol_matches(entity, alternative) for alternative in alternatives)
            # Source only where it can be cited directly: the best exact match (compact) or the top three (full).
            wants_source = include_source and (len(visible) < 3 if not compact else (exact and not any("source_excerpt" in v for v in visible)))
            if wants_source and entity.type in _STRUCTURAL | {"field", "compilation_unit", "data_item"}:
                result = entity_api.get_entity(entity_id=entity.id, project_id=project_id, db=db, user=user)
                definition = result.get("definition")
                if definition:
                    excerpt, clipped = _bounded(definition.get("content"), 2400 if compact else 1600)
                    item["source_excerpt"] = {
                        "start_line": definition["start_line"],
                        "end_line": definition["end_line"],
                        "source_ranges": definition.get("source_ranges", []),
                        "delivered_start_line": definition["start_line"],
                        "delivered_end_line": min(
                            definition["end_line"],
                            definition["start_line"] + max(0, len((excerpt or "").splitlines()) - 1),
                        ),
                        "content": excerpt,
                        "truncated": clipped,
                        "next_start_line": definition.get("next_start_line"),
                        "next_chunk_id": definition["chunk_id"] if clipped else definition.get("next_chunk_id"),
                        "next_char_offset": len(excerpt or "") if clipped else 0,
                    }
            visible.append(item)
        follow_up_actions = []
        for item in visible[: (1 if compact else 3)]:
            follow_up_actions.append({
                "tool": "explain_symbol",
                "arguments": {"project_id": project_id, "symbol": item["qualified_name"]},
                "reason": "Source, callers, callees and data access of this symbol in one call.",
            })
            if item["type"] in {"data_item", "sql_table", "file_fd", "record"}:
                follow_up_actions.append({
                    "tool": "trace_data_access",
                    "arguments": {"project_id": project_id, "entity_id": item["id"], "limit": 12},
                    "reason": "Inspect indexed reads and writes for this data entity.",
                })
        response = {
            "results": visible,
            "truncated": total > limit,
            "limit_applied": limit,
            "resolution": "none" if not visible else ("fuzzy" if "tokens" in modes else "exact"),
            "follow_up_actions": follow_up_actions[:3],
        }
        if not visible and suggestions:
            response["did_you_mean"] = suggestions[:5]
        _capture_mcp_result(ctx, db, project_id, response)
        return response


@mcp.tool(annotations=READ_ONLY)
def research_project(ctx: Context, project_id: int, query: str, limit: int = 8, hops: Annotated[int, Field(description="Traversal depth, 0-3; larger values are clamped to 3.")] = 2) -> dict:
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
            found_entities, _suggestions, _mode = _find_entities(db, user, project_id, term, limit)
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
            for entity in found_entities:
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
                match["call_flow"] = _call_flow_page(
                    db, user, project_id, exact[0]["id"], hops=hops, direction="outgoing",
                    scope="execution", page_size=10, cursor=None,
                    include_source=False,
                )
                match["follow_up_actions"] = [{
                    "tool": "explain_symbol",
                    "arguments": {"project_id": project_id, "symbol": exact[0]["qualified_name"]},
                    "reason": "Original source with line numbers, callers, callees and data access in one call.",
                }]
            elif not exact:
                match["follow_up_actions"] = [{
                    "tool": "search_code",
                    "arguments": {"project_id": project_id, "query": term, "limit": 8},
                    "reason": "No exact indexed symbol matched; search code content for the wording or business term.",
                }, {
                    "tool": "search_knowledge",
                    "arguments": {"project_id": project_id, "query": term, "limit": 5},
                    "reason": "The symbol search found no exact indexed entity; check project knowledge for a domain-level answer.",
                }]
            matches.append(match)

        if len(matches) == 1:
            match = matches[0]
            response = {
                "project_id": project_id, "query": query,
                "candidates": candidates[:limit], "candidate_count": len(candidates),
                "candidates_truncated": len(candidates) > limit,
                **match,
            }
        else:
            response = {
                "project_id": project_id, "query": query,
                "resolution": "multiple_queries", "matches": matches,
                "candidates": candidates[:limit], "candidate_count": len(candidates),
                "candidates_truncated": len(candidates) > limit,
                "notice": "Jedes explizite Symbol wurde getrennt aufgelöst; Mehrdeutigkeit bleibt pro Symbol sichtbar.",
            }
        _capture_mcp_result(ctx, db, project_id, response)
        return response


def _flow_summary(flow: dict, direction: str, limit: int = 12) -> list[dict]:
    nodes = {node.get("id"): node for node in flow.get("nodes", [])}
    items = []
    for edge in flow.get("edges", [])[:limit]:
        other = nodes.get(edge.get("target") if direction == "outgoing" else edge.get("source"))
        item = {
            "type": edge.get("type"),
            ("to" if direction == "outgoing" else "from"): (other or {}).get("qualified_name") or edge.get("target_name"),
            "line": edge.get("start_line"),
            "resolution": edge.get("resolution"),
        }
        if other and other.get("file_path"):
            item["location"] = f"{other['file_path']}:{other.get('start_line')}"
        items.append(item)
    return items


def _fact_line(buckets: dict[str, list[str]]) -> str:
    parts = []
    for label in ("calls", "performs", "cics", "datasets", "io"):
        names = [name.split("(", 1)[0][-48:] for name in (buckets.get(label) or [])]
        if names:
            parts.append(f"{label} {', '.join(names[:5])}")
    return "; ".join(parts)[:200]


def _outline(db: Session, entity: CodeEntity) -> list[dict]:
    """Children of a large entity with one-line facts per child (calls, performs, CICS commands, datasets)."""
    same_file = [
        CodeEntity.project_id == entity.project_id, CodeEntity.source_id == entity.source_id,
        CodeEntity.file_path == entity.file_path,
    ]
    children = db.query(CodeEntity).filter(
        *same_file, CodeEntity.id != entity.id, CodeEntity.type.in_(list(_STRUCTURAL)),
        CodeEntity.start_line >= entity.start_line, CodeEntity.end_line <= entity.end_line,
    ).order_by(CodeEntity.start_line, CodeEntity.id).limit(80).all()
    edges = db.query(CodeEdge).join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id).filter(
        CodeEdge.project_id == entity.project_id, *same_file,
        or_(
            CodeEdge.type.in_(["CALL", "CALLS", "PERFORM", "GOTO", "EXECUTES", "USES_DATASET"]),
            and_(CodeEdge.type.in_(["READS", "WRITES"]), func.json_extract_path_text(CodeEdge.meta_json, "io_target_kind").isnot(None)),
        ),
        CodeEdge.src_start_line >= entity.start_line, CodeEdge.src_start_line <= entity.end_line,
    ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(2500).all()
    labels = {"CALL": "calls", "CALLS": "calls", "PERFORM": "performs", "GOTO": "performs", "EXECUTES": "cics", "USES_DATASET": "datasets",
              "READS": "io", "WRITES": "io"}
    outline = []
    for child in children:
        buckets: dict[str, list[str]] = {}
        for edge in edges:
            if child.start_line <= (edge.src_start_line or 0) <= child.end_line and edge.dst_name:
                names = buckets.setdefault(labels[edge.type], [])
                label = edge.dst_name
                if edge.type in {"READS", "WRITES"}:
                    label = f"{(edge.meta_json or {}).get('operation') or edge.type} {edge.dst_name}"
                if label not in names:
                    names.append(label)
        item = {"symbol": child.qualified_name, "type": child.type, "lines": f"{child.start_line}-{child.end_line}"}
        facts = _fact_line(buckets)
        if facts:
            item["facts"] = facts
        outline.append(item)
    return outline


def _data_access_summary(db: Session, entity: CodeEntity, limit: int = 15) -> list[dict]:
    rows = db.query(CodeEdge).join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id).filter(
        CodeEdge.project_id == entity.project_id, CodeEntity.source_id == entity.source_id,
        CodeEntity.file_path == entity.file_path,
        CodeEdge.type.in_(["READS", "WRITES", "USES_DATASET"]),
        CodeEdge.src_start_line >= entity.start_line, CodeEdge.src_start_line <= entity.end_line,
    ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(400).all()
    groups: dict[tuple[str, str], dict] = {}
    for edge in rows:
        key = (edge.type, edge.dst_name or "")
        group = groups.setdefault(key, {"access": edge.type, "target": edge.dst_name, "lines": []})
        if len(group["lines"]) < 4:
            group["lines"].append(edge.src_start_line)
        meta = edge.meta_json or {}
        if meta.get("operation") and "operation" not in group:
            group["operation"] = meta["operation"]
        if meta.get("io_target_kind"):
            group["file_io"] = True
    order = {"WRITES": 0, "USES_DATASET": 1, "READS": 2}
    return sorted(groups.values(), key=lambda g: (0 if g.get("file_io") else 1, order.get(g["access"], 3), g["lines"][0] or 0))[:limit]


@mcp.tool(annotations=READ_ONLY)
def explain_symbol(
    ctx: Context,
    project_id: int,
    symbol: str,
    max_chars: Annotated[int, Field(description="Response budget for source and facts, 1500-12000.")] = 7000,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict:
    """FIRST CHOICE for any named class, method, program or paragraph: everything in ONE call.

    Resolves ``Klasse.methode``, ``Klasse#methode``, ``PROGRAM`` or ``PROGRAM.PARAGRAPH`` and returns the original
    source with line numbers, callers, callees and indexed data access. For a large program or class it returns an
    outline instead: every paragraph or method with its line range and facts (calls, performs, CICS commands,
    datasets). Then call ``explain_symbol`` again with one outline ``symbol``. Use ``start_line``/``end_line``
    to read a specific range of the same symbol.
    """
    max_chars = max(1500, min(max_chars, 12000))
    symbol = symbol.strip()
    if start_line is not None and start_line < 1:
        raise ValueError("invalid start_line")
    if end_line is not None and (end_line < 1 or (start_line is not None and end_line < start_line)):
        raise ValueError("invalid end_line")
    with _tool_context(ctx, "explain_symbol", project_id, {"max_chars": max_chars, "start_line": start_line, "end_line": end_line}) as (db, user):
        if not symbol or len(symbol) > 200:
            raise ValueError("invalid symbol")
        _project(db, user, project_id)
        found, suggestions, mode = _find_entities(db, user, project_id, symbol, 8)
        exact = [e for e in found if _symbol_matches(e, symbol)] or found
        structural = [e for e in exact if e.type in _STRUCTURAL] or exact
        if not structural:
            response = {"project_id": project_id, "symbol": symbol, "resolution": "none", "did_you_mean": suggestions,
                        "hint": "No indexed symbol matched. Try search_code with a shorter name or search_knowledge for wording."}
            _capture_mcp_result(ctx, db, project_id, response)
            return response
        entity, others = _pick_entity(structural)
        if entity is None:
            response = {"project_id": project_id, "symbol": symbol, "resolution": "ambiguous",
                        "candidates": [_compact_entity(e) for e in structural[:8]],
                        "hint": "Call explain_symbol again with one qualified_name from candidates."}
            _capture_mcp_result(ctx, db, project_id, response)
            return response
        low = start_line if start_line is not None else entity.start_line or 1
        high = end_line if end_line is not None else entity.end_line or 10**9
        pieces: list[tuple[int, str]] = []
        for chunk in entity_api._definition_chunks(entity, db, start_line=start_line, end_line=end_line):
            first, last = max(low, chunk.start_line), min(high, chunk.end_line)
            if first > last:
                continue
            lines = chunk.content.splitlines()
            pieces.append((first, "\n".join(lines[first - chunk.start_line:last - chunk.start_line + 1])))
        source_budget = int(max_chars * 0.65)
        total_chars = sum(len(text) for _first, text in pieces)
        outline = None
        source = None
        if start_line is None and end_line is None and total_chars > source_budget:
            outline = _outline(db, entity)
        if not outline:
            outline = None
            parts, used, truncated, next_line, last_delivered = [], 0, False, None, None
            for first, text in pieces:
                room = source_budget - used
                if room <= 0:
                    truncated, next_line = True, first
                    break
                clipped = text[:room]
                if len(clipped) < len(text):
                    clipped = clipped[: clipped.rfind("\n")] if "\n" in clipped else clipped
                    truncated = True
                parts.append(_numbered(clipped, first))
                used += len(clipped)
                last_delivered = first + max(0, len(clipped.splitlines()) - 1)
                if truncated:
                    next_line = last_delivered + 1
                    break
            source = {
                "start_line": pieces[0][0] if pieces else entity.start_line,
                "end_line": last_delivered if last_delivered is not None else entity.end_line,
                "text": "\n".join(parts), "truncated": truncated, "next_start_line": next_line,
            }
        response = {
            "project_id": project_id, "symbol": symbol,
            "resolution": "unique_exact_match" if mode == "exact" and not others else ("overloads" if others else "fuzzy"),
            "entity": _compact_entity(entity),
        }
        if source is not None:
            response["source"] = source
        else:
            kept, size = [], 0
            for item in outline:
                size += len(json.dumps(item, ensure_ascii=False))
                if size > max_chars and kept:
                    break
                kept.append(item)
            response["outline"] = kept
            if len(kept) < len(outline):
                response["outline_omitted"] = len(outline) - len(kept)
            response["notice"] = "Source not inlined (larger than the budget). Call explain_symbol with one outline symbol."
        if source is not None:
            try:
                callees = _flow_summary(_call_flow_page(db, user, project_id, entity.id, hops=1, direction="outgoing",
                                                        scope="execution", page_size=12, cursor=None, include_source=False), "outgoing")
                callers = _flow_summary(_call_flow_page(db, user, project_id, entity.id, hops=1, direction="incoming",
                                                        scope="execution", page_size=8, cursor=None, include_source=False), "incoming", 8)
            except (ValueError, HTTPException):
                callees, callers = [], []
            if callees:
                response["callees"] = callees
            if callers:
                response["callers"] = callers
            access = _data_access_summary(db, entity)
            if access:
                response["data_access"] = access
        if others:
            response["other_matches"] = [_compact_entity(e) for e in others[:6]]
        if source is not None and source["truncated"] and source["next_start_line"]:
            response["follow_up_actions"] = [{
                "tool": "explain_symbol",
                "arguments": {"project_id": project_id, "symbol": entity.qualified_name,
                              "start_line": source["next_start_line"], "end_line": entity.end_line, "max_chars": max_chars},
                "reason": "Continue reading the rest of this symbol.",
            }]
        _capture_mcp_result(ctx, db, project_id, response)
        return response


@mcp.tool(annotations=READ_ONLY)
def get_code_entity(
    ctx: Context,
    project_id: int,
    entity_id: int | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    max_chars: int = 5000,
    chunk_id: int | None = None,
    char_offset: int = 0,
    symbol: Annotated[str | None, Field(description="Qualified name instead of entity_id, e.g. Klasse#methode or PROGRAM.PARAGRAPH.")] = None,
) -> dict:
    """Read an indexed entity with paged, line-attributed original source.

    Pass ``entity_id`` or, without a prior search, a ``symbol`` name. ``explain_symbol`` returns more in one call.
    """
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
        if entity_id is None:
            if not symbol:
                raise ToolInputError("entity_id or symbol required")
            _project(db, user, project_id)
            entity = _resolve_symbol(db, user, project_id, symbol.strip())
        else:
            entity = _entity(db, user, project_id, entity_id)
        source_chunks = entity_api._definition_chunks(
            entity, db, start_line=start_line, end_line=end_line
        )
        if chunk_id is not None:
            # Resume inside the entity's ordered chunk list so later chunks are
            # not lost after the continued one.
            ids = [chunk.id for chunk in source_chunks]
            if chunk_id not in ids:
                raise ValueError("invalid cursor")
            source_chunks = source_chunks[ids.index(chunk_id):]
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
        response = {
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
                        "start_line": start_line,
                        "end_line": end_line,
                        "chunk_id": next_chunk_id,
                        "char_offset": next_char_offset,
                        "max_chars": max_chars,
                    },
                    "reason": "Continue reading the remaining indexed source segment.",
                }] if has_more else [],
            } if sections else None,
        }
        _capture_mcp_result(ctx, db, project_id, response)
        return response


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
        response = {
            "project_id": project_id,
            "entity": {"id": entity.id, "name": entity.name, "type": entity.type},
            "accesses": accesses,
            "accesses_returned": len(accesses),
            "truncated": truncated,
            "notice": "Indexierte READS/WRITES in Quellreihenfolge; kein vollständiger Kontrollfluss- oder Laufzeitbeweis.",
        }
        _capture_mcp_result(ctx, db, project_id, response)
        return response


def _call_flow_page(
    db: Session, user: User, project_id: int, entity_id: int, *, hops: int,
    direction: str, scope: str, page_size: int, cursor: str | None, include_source: bool,
) -> dict:
    """One ACL-filtered, cursor-paged call-flow page shared by all MCP entry points."""
    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError("invalid direction")
    if scope not in {"execution", "dependencies", "all"}:
        raise ValueError("invalid scope")
    requested_root = _entity(db, user, project_id, entity_id)
    offset = 0
    expansion = 0
    if cursor is not None:
        try:
            padding = "=" * (-len(cursor) % 4)
            cursor_data = json.loads(base64.urlsafe_b64decode(cursor + padding))
        except (ValueError, TypeError, binascii.Error):
            raise ValueError("invalid cursor")
        if not isinstance(cursor_data, dict):
            raise ValueError("invalid cursor")
        expected = {
            "project_id": project_id, "entity_id": entity_id, "hops": hops,
            "direction": direction, "scope": scope, "include_source": include_source,
        }
        if any(cursor_data.get(key) != value for key, value in expected.items()):
            raise ValueError("cursor does not match this call-flow query")
        offset = cursor_data.get("offset")
        if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= 10_000:
            raise ValueError("invalid cursor")
        expansion = cursor_data.get("expansion", 0)
        if not isinstance(expansion, int) or isinstance(expansion, bool) or not 0 <= expansion <= 100:
            raise ValueError("invalid cursor")

    node_limit = min(1_000, max(
        CALL_FLOW_MAX_NODES, offset + page_size * 2 + 1 + expansion * page_size * 2
    ))
    edge_limit = min(3_000, max(
        CALL_FLOW_MAX_EDGES, offset + page_size + 1 + expansion * page_size
    ))
    result = trace_call_flow(
        db, project_id=project_id, entity_id=entity_id, hops=hops,
        direction=direction, scope=scope, node_limit=node_limit, edge_limit=edge_limit,
    )
    raw_nodes = result.get("nodes", [])
    source_access = {}
    visible_nodes_by_id = {}
    for node in raw_nodes:
        source_id = node.get("source_id")
        if source_id not in source_access:
            source_access[source_id] = _source_visible(db, user, source_id)
        if source_access[source_id]:
            visible_nodes_by_id[node.get("id")] = node
    raw_edges = result.get("edges", [])
    visible_edges = [
        edge for edge in raw_edges
        if edge.get("source") in visible_nodes_by_id
        and (edge.get("target") is None or edge.get("target") in visible_nodes_by_id)
    ]
    page_edges = visible_edges[offset:offset + page_size]
    page_node_ids = []
    root_id = (result.get("root") or {}).get("id")
    for node_id in [root_id, *[
        node_id
        for edge in page_edges
        for node_id in (edge.get("source"), edge.get("target"))
        if node_id is not None
    ]]:
        if node_id in visible_nodes_by_id and node_id not in page_node_ids:
            page_node_ids.append(node_id)
    nodes = [visible_nodes_by_id[node_id] for node_id in page_node_ids]
    allowed = set(page_node_ids)
    edges = []
    source_budget_per_edge = max(120, min(500, 4_000 // max(1, len(page_edges))))
    for edge in page_edges:
        if edge.get("source") not in allowed or (edge.get("target") is not None and edge.get("target") not in allowed):
            continue
        meta = edge.get("meta") or {}
        response_edge = {
            **{key: edge.get(key) for key in (
                "id", "source", "target", "target_name", "type", "resolution", "start_line", "end_line"
            )},
            "resolution_evidence": {
                key: meta[key]
                for key in (
                    "target_qualified_name", "target_file_path", "resolution_reason",
                    "resolution_scope", "receiver", "receiver_resolution",
                    "receiver_symbol_qualified_name", "receiver_type_qualified_name",
                    "receiver_method_qualified_name", "argument_count", "argument_types",
                    "argument_expressions", "control_role", "control_context",
                    "exception_types", "dispatch_scope",
                ) if key in meta
            },
        }
        if include_source:
            response_edge["source_excerpt"] = _flow_edge_excerpt(
                db, project_id, visible_nodes_by_id[edge["source"]],
                edge, source_budget_per_edge,
            )
        edges.append(response_edge)

    next_offset = offset + len(page_edges)
    page_has_more = next_offset < len(visible_edges)
    service_truncated = bool(result.get("truncated"))
    can_expand = node_limit < 1_000 or edge_limit < 3_000
    has_more = page_has_more or (service_truncated and can_expand)
    next_cursor = None
    if has_more:
        next_data = {
            "project_id": project_id, "entity_id": entity_id, "hops": hops,
            "direction": direction, "scope": scope, "include_source": include_source,
            "offset": next_offset,
            "expansion": expansion + int(service_truncated and not page_has_more),
        }
        next_cursor = base64.urlsafe_b64encode(
            json.dumps(next_data, sort_keys=True, separators=(",", ":")).encode()
        ).decode().rstrip("=")
    truncated = has_more or len(visible_nodes_by_id) > len(nodes) or len(visible_edges) > len(edges)
    root = result.get("root")
    if not root or root.get("id") not in visible_nodes_by_id:
        root = {
            "id": requested_root.id, "name": requested_root.name,
            "qualified_name": requested_root.qualified_name, "type": requested_root.type,
            "file_path": requested_root.file_path, "source_id": requested_root.source_id,
            "start_line": requested_root.start_line, "end_line": requested_root.end_line,
        }
    response = {
        "project_id": project_id,
        "status": result.get("status"),
        "notice": result.get("notice"),
        "root": root,
        "entry_resolution": result.get("entry_resolution"),
        "hops_applied": hops,
        "scope": scope,
        "entry_candidates": result.get("entry_candidates", [])[:20],
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "limit_applied": page_size,
        "truncation": {
            "reason": "page_has_more" if page_has_more else (
                "service_limit" if service_truncated else (
                    "source_visibility" if len(visible_edges) < len(raw_edges) else None
                )
            ),
            "nodes_returned": len(nodes),
            "nodes_available": len(visible_nodes_by_id),
            "nodes_omitted": max(0, len(visible_nodes_by_id) - len(nodes)),
            "edges_returned": len(edges),
            "edges_available": len(visible_edges),
            "edges_omitted": max(0, len(visible_edges) - len(edges)),
            "next_cursor": next_cursor,
            "source_visibility_filtered": len(visible_edges) < len(raw_edges)
                or len(visible_nodes_by_id) < len(raw_nodes),
            "service_truncated": service_truncated,
            "continuation_limit_reached": service_truncated and not can_expand,
        },
        "follow_up_actions": [{
            "tool": "get_call_flow",
            "arguments": {
                "project_id": project_id, "entity_id": entity_id, "hops": hops,
                "direction": direction, "scope": scope, "page_size": page_size,
                "cursor": next_cursor, "include_source": include_source,
            },
            "reason": "Continue the ordered visible call-flow page.",
        }] if next_cursor else [],
    }
    return response


@mcp.tool(annotations=READ_ONLY)
def get_call_flow(
    ctx: Context,
    project_id: int,
    entity_id: int,
    hops: Annotated[int, Field(description="Traversal depth, 0-3; larger values are clamped to 3 (see hops_applied).")] = 2,
    direction: Literal["outgoing", "incoming", "both"] = "outgoing",
    scope: Literal["execution", "dependencies", "all"] = "execution",
    page_size: Annotated[int, Field(description="Edges per page, 1-15; larger values are clamped to 15 (see limit_applied).")] = 10,
    cursor: Annotated[str | None, Field(description="Opaque next_cursor from the previous page, passed back byte-for-byte unchanged, together with the same entity_id, hops, direction, scope and include_source.")] = None,
    include_source: bool = True,
) -> dict:
    """Trace executable calls or resource/data dependencies in a project.

    ``scope`` selects ``execution`` (CALL/PERFORM/etc.), ``dependencies``
    (COPY/import/resource/data edges), or ``all``. ``direction`` is outgoing,
    incoming, or both. Continue a large result with the returned ``next_cursor``
    and the same root, hops, direction, and scope.
    """
    hops = max(0, min(hops, 3))
    page_size = max(1, min(page_size, 15))
    with _tool_context(ctx, "get_call_flow", project_id, {
        "entity_id": entity_id, "hops": hops, "scope": scope,
        "direction": direction, "page_size": page_size, "cursor": cursor,
        "include_source": include_source,
    }) as (db, user):
        response = _call_flow_page(
            db, user, project_id, entity_id, hops=hops, direction=direction, scope=scope,
            page_size=page_size, cursor=cursor, include_source=include_source,
        )
        _capture_mcp_result(ctx, db, project_id, response)
        return response


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
        response = {
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
        _capture_mcp_result(ctx, db, project_id, response)
        return response


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
        retrieval_mode = "semantic"
        try:
            chunks = await search_project_chunks(
                db, project_id, query, limit=limit + 1, **embedding_config
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, OSError) as exc:
            logger.warning("MCP search_knowledge embedding failed (%s); using lexical fallback", type(exc).__name__)
            retrieval_mode = "lexical_fallback"
            chunks = _lexical_project_chunks(db, project_id, query, limit + 1)
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
        response = {"results": results, "truncated": len(chunks) > limit or len(results) < min(len(chunks), limit), "limit_applied": limit, "retrieval_mode": retrieval_mode, "notice": (
            "Semantic similarity is a retrieval hint, not a verified conclusion."
            if retrieval_mode == "semantic" else
            "The embedding service is unavailable; results come from a keyword match, "
            "not semantic similarity. Use search_code or get_code_entity for source-backed evidence."
        )}
        _capture_mcp_result(ctx, db, project_id, response)
        return response


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
_mcp_manager_used = False


@asynccontextmanager
async def run_mcp_session_manager():
    """Lifespan-Klammer fuer den MCP-Session-Manager.

    Der SDK-Manager kann nur einmal pro Instanz laufen. Produktiv gibt es genau einen
    App-Lifespan; Tests und Reloads durchlaufen ihn aber mehrfach im selben Prozess.
    Ab dem zweiten Lauf bauen wir Manager und ASGI-App frisch auf.
    """
    global _mcp_manager_used
    if _mcp_manager_used:
        mcp._session_manager = None
        asgi_app.app = mcp.streamable_http_app()
    _mcp_manager_used = True
    async with mcp.session_manager.run():
        yield
