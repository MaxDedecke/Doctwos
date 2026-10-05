"""Read-only inbound MCP transport and tools for IDE clients."""

from contextlib import asynccontextmanager
import logging
import base64
import binascii
import asyncio
import concurrent.futures
import hashlib
import json
import math
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
from services.ollama_client import embed_text, search_project_chunks
from services.search import search_nodes
from core.language_profile import role_of
from services import evidence as evidence_blocks
from services.source_access import COMMENT_START as _COMMENT_START
from services.source_access import numbered as _numbered
from services.source_access import site_excerpt as _site_excerpt
from services.source_access import source_visible as _source_visible


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
            # COBOL-Programm- und Copybook-Namen ohne Bindestrich (COSGN00C, CBTRN03C): Großbuchstaben mit Ziffer.
            or re.fullmatch(r"(?=[A-Z0-9]*[0-9])(?=[A-Z0-9]*[A-Z])[A-Z][A-Z0-9]{3,}", part)
        )

    if len(pieces) > 1 and all(symbol_like(part) for part in pieces):
        return pieces[:8]
    return [term] if term else []


_MENTION_PATTERNS = (
    re.compile(r"\b(?=[A-Z0-9-]*[0-9])(?=[A-Z0-9-]*[A-Z])[A-Z][A-Z0-9-]{3,}\b"),  # COSGN00C, CBTRN03C
    re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b"),  # PA-TRANSACTION-AMT
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b"),  # UserLogic
    re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+)+\b"),  # doCreate
    re.compile(r"\b[A-Za-z_]\w*(?:[#.][A-Za-z_]\w*)+\b"),  # UserLogic.create, Class#method
)


def _mentioned_symbols(text: str, limit: int = 4) -> list[str]:
    """Symbol-like names inside a prose question (``Welche Rolle spielt COSGN00C bei der Anmeldung?``).

    The names are only candidates: ``research_project`` keeps those that resolve to an indexed entity."""
    plain = text.replace("`", " ")
    found: list[str] = []
    for pattern in _MENTION_PATTERNS:
        for token in pattern.findall(plain):
            token = token.rstrip(".")
            if len(token) >= 4 and token.casefold() not in {item.casefold() for item in found}:
                found.append(token)
    return found[:limit]


def _symbol_key(value: str | None) -> str:
    value = (value or "").replace("\\", "/").casefold()
    value = value.split("(", 1)[0].replace("#", ".")
    return re.sub(r"\s+", "", value).strip(".")


def _split_params(text: str) -> list[str]:
    """Split a parameter list at top-level commas; generic arguments keep theirs."""
    parts, depth, current = [], 0, ""
    for char in text:
        if char in "<(":
            depth += 1
        elif char in ">)":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current)
    return parts


def _param_type(param: str) -> str:
    """Parameter type without modifiers or a trailing parameter name (``final UserUR req`` -> ``userur``)."""
    param = re.sub(r"\b(?:final)\b", " ", param.strip())
    named = re.match(r"^(.*[>\]\w])\s+[\w$]+$", param.strip())
    return re.sub(r"\s+", "", (named.group(1) if named else param)).casefold()


def _query_signature(term: str) -> list[str] | None:
    """Parameter types a query asks for, ``None`` when it names no signature."""
    match = re.search(r"\((.*)\)\s*$", term.strip())
    return [_param_type(part) for part in _split_params(match.group(1))] if match else None


def _entity_signature(entity: CodeEntity) -> list[str] | None:
    """Parameter types of a method/constructor (``Klasse#name(A,B)``); ``None`` for everything else."""
    match = re.search(r"#[^#@()]*\((.*)\)$", entity.qualified_name or "")
    return [_param_type(part) for part in _split_params(match.group(1))] if match else None


def _symbol_matches(entity: CodeEntity, term: str) -> bool:
    wanted = _query_signature(term)
    if wanted is not None and _entity_signature(entity) != wanted:
        return False
    return _symbol_name_matches(entity, term)


def _symbol_name_matches(entity: CodeEntity, term: str) -> bool:
    needle = _symbol_key(term)
    name = _symbol_key(entity.name)
    qualified = _symbol_key(entity.qualified_name)
    path = _symbol_key(entity.file_path)
    if needle in {name, qualified, path}:
        return True
    return bool(needle and (qualified.endswith("." + needle) or path.endswith("/" + needle)))


_DOTTED = re.compile(r"^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+$")
_NOISE_TYPES = {"parameter", "local_variable", "local", "record_component"}
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
    if found and len(term.split()) > 1 and not any(
        _symbol_matches(entity, variant) for entity in found for variant in _query_variants(term)
    ):
        # `search_nodes` löst Mehrwortbegriffe selbst auf (UND über die Teilbegriffe); das ist kein exakter Symboltreffer.
        mode = "tokens"
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
        "Doctus indexes source code. For a question about code call answer_context first with the question text: "
        "it resolves the named classes, methods, programs and copybooks and returns source with line numbers, "
        "callers, callees, data access and users in one call. Use explain_symbol for one named symbol, "
        "search_code only to discover names, search_knowledge for wording or business terms. "
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



_USED_BY_TYPES = ["CALL", "CALLS", "PERFORM", "GOTO", "COPY", "EXTENDS", "IMPLEMENTS", "INSTANTIATES", "REFERENCES_METHOD"]


def _used_by(db: Session, user: User, entity: CodeEntity, limit: int = 12) -> list[dict]:
    """Source units that reference this entity (callers, COPY users, subclasses); overloads count together."""
    dst_ids = [entity.id]
    if entity.type in {"method", "constructor"} and entity.qualified_name and "(" in entity.qualified_name:
        prefix = entity.qualified_name.split("(", 1)[0] + "("
        dst_ids += [row.id for row in db.query(CodeEntity.id).filter(
            CodeEntity.project_id == entity.project_id, CodeEntity.type.in_(["method", "constructor"]),
            CodeEntity.qualified_name.like(prefix + "%"), ~CodeEntity.qualified_name.like("%@%"),
            CodeEntity.id != entity.id).limit(20).all()]
    rows = db.query(CodeEdge, CodeEntity).join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id).filter(
        CodeEdge.project_id == entity.project_id, CodeEdge.type.in_(_USED_BY_TYPES),
        or_(CodeEdge.dst_entity_id.in_(dst_ids),
            and_(CodeEdge.dst_entity_id.is_(None), CodeEdge.dst_name == entity.name)),
    ).order_by(CodeEntity.file_path, CodeEdge.src_start_line).limit(400).all()
    visible: dict[int | None, bool] = {}
    units: dict[str, dict] = {}
    for edge, src in rows:
        if src.source_id not in visible:
            visible[src.source_id] = _source_visible(db, user, src.source_id)
        if not visible[src.source_id] or src.file_path == entity.file_path:
            continue
        unit = units.setdefault(src.file_path, {
            "unit": (src.file_path or "").rsplit("/", 1)[-1].rsplit(".", 1)[0], "file": src.file_path,
            "types": [], "lines": [], "resolution": edge.resolution,
        })
        if edge.type not in unit["types"]:
            unit["types"].append(edge.type)
        if edge.src_start_line and len(unit["lines"]) < 3:
            unit["lines"].append(edge.src_start_line)
    items = list(units.values())
    return items[:limit] if limit else items


_SYMBOL_PATTERNS = [
    # COBOL: Programm.Absatz (`COPAUA0C.MAIN-PARA`, `COPAUA0C.1000-INITIALIZE`) und Absatznamen mit führender Zahl.
    re.compile(r"\b[A-Z][A-Z0-9]*\.[0-9A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b"),
    re.compile(r"\b[0-9]{2,5}-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*\b"),
    re.compile(r"\b[A-Za-z_$][\w$]*(?:[.#][A-Za-z_$][\w$]*)+(?:\(\))?"),
    re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b"),
    re.compile(r"\b[A-Z]{2,}[0-9][A-Z0-9]*\b"),
    re.compile(r"\b[A-Z][A-Z0-9]{4,}\b"),
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b"),
    re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]*)+\b"),
    re.compile(r"\b[A-Z]{2,}[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)*\b"),
    re.compile(r"\b[\w./-]+\.(?:cbl|cpy|java|xml)\b", re.I),
]
_NOT_SYMBOLS = {"z.b", "d.h", "u.a", "usw", "bzw", "e.g", "i.e", "etc", "cobol", "batch", "vsam", "cics", "json", "sql", "java", "http", "https"}


def _extract_symbols(question: str) -> list[str]:
    """Names that look like code symbols in free text, in order of appearance, longest forms first."""
    found: list[tuple[int, str]] = []
    for pattern in _SYMBOL_PATTERNS:
        for match in pattern.finditer(question):
            term = match.group(0).rstrip(".,;:").removesuffix("()")
            if len(term) >= 4 and term.casefold() not in _NOT_SYMBOLS:
                found.append((match.start(), term))
    found.sort(key=lambda item: (item[0], -len(item[1])))
    terms: list[str] = []
    for _pos, term in found:
        key = term.casefold()
        if any(key == t.casefold() or key in t.casefold() for t in terms):
            continue
        terms = [t for t in terms if t.casefold() not in key] + [term]
    return terms[:8]


_CHILD_SKIP = {"section", "constructor"}
_HOUSEKEEPING = re.compile(r"OPEN|CLOSE|ABEND|DISPLAY-IO|IO-STATUS|TIMESTAMP|INIT-|^Z-|ERROR-", re.I)
_DE_EN = {
    "ablehn": "reject fail invalid error", "zins": "interest rate", "datei": "dataset", "gelesen": "read",
    "lies": "read", "geschrieb": "write", "schreib": "write", "berechn": "compute calc", "anmeld": "signon login auth",
    "benutz": "user", "konto": "acct account", "karte": "card xref", "transakt": "tran transaction", "summe": "total",
    "bericht": "report rept", "menü": "menu", "menue": "menu", "prüf": "valid check edit lookup", "pruef": "valid check edit lookup",
    "validier": "valid check lookup", "formel": "compute calc", "buchung": "post write tran tx", "aktualis": "update", "anleg": "add create", "lösch": "delete", "sperr": "suspend lock",
    "passwort": "password pwd", "fehler": "error fail", "buch": "post", "weiterleit": "xctl link", "aufruf": "call",
    "authentifiz": "authenticate auth", "ausnahme": "exception", "regel": "rule policy", "richtlinie": "policy",
    "benachricht": "notification notify", "aufgabe": "task job", "erzeug": "create build", "gruppe": "group",
}


_GENERIC_WORDS = {
    "nenne", "nennen", "welche", "welcher", "welches", "welchen", "wird", "werden", "wurde", "batch", "programm", "programme", "program",
    "datei", "dateien", "file", "files", "nach", "ende", "eine", "einer", "einen", "dass", "beschreibe", "erkläre", "erklaere", "gelesenen",
    "geschrieben", "angepasst", "carddemo", "syncope", "apache", "cobol", "java", "klasse", "methode", "funktion", "ablauf", "läuft", "laeuft",
    "wenn", "oder", "sowie", "dabei", "dafür", "dafuer", "sich", "nicht", "ihre", "ihrer", "alle", "wann", "womit", "wozu",
}


def _question_stems(question: str) -> set[str]:
    """First five letters of the question words plus English code words for common German terms."""
    lowered = question.lower()
    stems = {t[:5] for t in re.findall(r"[a-zäöüß0-9]{4,}", lowered) if t not in _GENERIC_WORDS}
    for german, english in _DE_EN.items():
        if german in lowered:
            stems |= {t[:5] for t in english.split()}
    return stems


def _relevant_children(question: str, outline: list[dict], count: int = 6, sims=None) -> list[dict]:
    """Outline entries that cover the question: greedy by word overlap (names count double, already covered words
    do not count again), orchestration and embedding similarity as extras, then one step along PERFORM."""
    q_stems = _question_stems(question)
    entries = []
    for position, item in enumerate(outline):
        if item.get("type") in _CHILD_SKIP:
            continue
        tail = re.split(r"[.#]", item["symbol"].split("(", 1)[0])[-1]
        facts = item.get("facts", "")
        plain_facts = re.sub(r"(?:^|; )(?:calls|performs|cics|datasets|io|computes|sets|msgs) ", " ", facts)
        name_tokens = {t[:5] for t in re.findall(r"[a-zäöüß0-9]{3,}", tail.lower().replace("-", " "))}
        fact_tokens = {t[:5] for t in re.findall(r"[a-zäöüß0-9]{3,}", plain_facts.lower().replace("-", " "))}
        name_hit = q_stems & name_tokens
        fact_hit = (q_stems & fact_tokens) - name_hit
        # A paragraph or method that drives many others (PERFORM/CALL fan-out) usually carries the main flow.
        fan_out = facts.count(",") + (1 if facts else 0)
        base = min(3, fan_out // 3)
        if re.search(r"MAIN|PROCESS|EXECUTE|RUN", tail.upper()):
            base += 1
        if "xctl" in facts.lower() or "link" in facts.lower():
            if re.search(r"gestartet|startet|weiterleit|aufruf|weiter|programm|ruft", question.lower()):
                base += 2
        if _HOUSEKEEPING.search(tail) and not _HOUSEKEEPING.search(question):
            base -= 3
        entries.append({"item": item, "pos": position, "name": name_hit, "fact": fact_hit, "base": base})
    if sims is not None and entries:
        preliminary = sorted(entries, key=lambda e: -(2 * len(e["name"]) + len(e["fact"]) + e["base"]))[:12]
        similarity = sims([e["item"] for e in preliminary]) or {}
        for entry in preliminary:
            entry["base"] += 8.0 * max(0.0, similarity.get(entry["item"]["symbol"], 0.0))
    covered: set[str] = set()
    chosen: list[dict] = []
    remaining = list(entries)
    while remaining and len(chosen) < count:
        def gain(e: dict) -> float:
            return 2 * len(e["name"] - covered) + len(e["fact"] - covered) + e["base"]
        best = max(remaining, key=lambda e: (gain(e), -e["pos"]))
        if gain(best) <= 0:
            break
        chosen.append(best["item"])
        covered |= best["name"] | best["fact"]
        remaining.remove(best)
    if not chosen:
        chosen = [e["item"] for e in entries[:count]]
    # One step further along the PERFORM chain: the paragraph a best match hands over to often holds the rest of the
    # answer (e.g. the posting written by the computation paragraph).
    by_tail = {re.split(r"[.#]", i["symbol"].split("(", 1)[0])[-1].upper(): i for i in outline if i.get("type") not in _CHILD_SKIP}
    extras: list[dict] = []
    for item in chosen[:2]:
        performed = re.search(r"performs ([^;]*)", item.get("facts", ""))
        for name in (performed.group(1).split(", ") if performed else []):
            target = by_tail.get(name.strip().upper())
            if target and target not in chosen and target not in extras and not _HOUSEKEEPING.search(name):
                extras.append(target)
    return (chosen + extras)[: count + 1]


def _explain_entity(
    db: Session, user: User, project_id: int, entity: CodeEntity, others: list[CodeEntity], mode: str, symbol: str,
    max_chars: int, start_line: int | None, end_line: int | None, *, with_context: bool = True, used_by_limit: int = 12,
    compact: bool = False,
) -> dict:
    """Source (or outline for large entities), callees, callers, data access and users of one entity."""
    low = start_line if start_line is not None else entity.start_line or 1
    high = end_line if end_line is not None else entity.end_line or 10**9
    pieces: list[tuple[int, str]] = []
    for chunk in entity_api._definition_chunks(entity, db, start_line=start_line, end_line=end_line):
        first, last = max(low, chunk.start_line), min(high, chunk.end_line)
        if first > last:
            continue
        lines = chunk.content.splitlines()
        pieces.append((first, "\n".join(lines[first - chunk.start_line:last - chunk.start_line + 1])))
    source_budget = int(max_chars * (0.65 if with_context else 0.92))
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
            parts.append(_numbered(clipped, first, compact))
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
    if source is not None and with_context:
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
    if with_context:
        used_by = _used_by(db, user, entity, used_by_limit)
        if used_by:
            response["used_by"] = used_by
    if others:
        response["other_matches"] = [_compact_entity(e) for e in others[:6]]
    if source is not None and source["truncated"] and source["next_start_line"]:
        response["follow_up_actions"] = [{
            "tool": "explain_symbol",
            "arguments": {"project_id": project_id, "symbol": entity.qualified_name,
                          "start_line": source["next_start_line"], "end_line": entity.end_line, "max_chars": max_chars},
            "reason": "Continue reading the rest of this symbol.",
        }]
    return response


def _shrink_largest_source(entry: dict) -> bool:
    """Cut the last fifth of the longest expanded/helper/chain source (whole lines, at least 4 kept)."""
    parts = [p for key in ("expanded", "helper_methods", "callee_chain") for p in entry.get(key) or [] if (p.get("source") or {}).get("text")]
    if not parts:
        return False
    target = max(parts, key=lambda p: len(p["source"]["text"]))
    lines = target["source"]["text"].splitlines()
    if len(lines) <= 4:
        return False
    keep = max(4, int(len(lines) * 0.8))
    target["source"]["text"] = "\n".join(lines[:keep])
    target["source"]["truncated"] = True
    return True


def _fit_evidence(evidence: list[dict], limit: int) -> None:
    """Shrink an evidence pack in steps until it fits.

    Order: redundant extras first (a control-flow block makes ``callees`` and ``callee_chain`` redundant), then lists,
    never the primary source and last of all the evidence blocks (includes, control flow, data origin) that answer
    the question directly."""
    def size() -> int:
        return len(json.dumps(evidence, ensure_ascii=False))

    def trim_sites(entry: dict) -> bool:
        trimmed = False
        for site in entry.get("call_sites") or []:
            if isinstance(site, dict) and len(site.get("text") or "") > 700:
                site["text"] = site["text"][:700]
                trimmed = True
        return trimmed

    def trim_includes(entry: dict) -> bool:
        block = entry.get("includes")
        if not block or not any(len(block[key]) > 14 for key in ("resolved", "external", "unresolved")):
            return False
        for key in ("resolved", "external", "unresolved"):
            del block[key][14:]
        block["truncated"] = True
        return True

    def trim_flow(entry: dict) -> bool:
        flow = (entry.get("control_flow") or {}).get("flow")
        if not flow or len(flow) <= 6:
            return False
        flow.pop()
        return True

    steps = [
        lambda e: e.pop("other_matches", None),
        _shrink_largest_source,
        lambda e: e.get("control_flow") and (e.pop("callees", None) or e.pop("callee_chain", None)),
        trim_sites,
        lambda e: e.__setitem__("data_access", e["data_access"][:6]) if len(e.get("data_access") or []) > 6 else None,
        lambda e: e.__setitem__("used_by", e["used_by"][:8]) if len(e.get("used_by") or []) > 8 else None,
        lambda e: e.__setitem__("callers", e["callers"][:3]) if len(e.get("callers") or []) > 3 else None,
        lambda e: e.__setitem__("callees", e["callees"][:6]) if len(e.get("callees") or []) > 6 else None,
        lambda e: e.get("call_sites") and len(e["call_sites"]) > 1 and e["call_sites"].pop(),
        lambda e: e.pop("call_sites", None),
        lambda e: e.pop("data_access", None),
        lambda e: e.get("expanded") and len(e["expanded"]) > 1 and e["expanded"].pop(),
        lambda e: e.get("helper_methods") and len(e["helper_methods"]) > 1 and e["helper_methods"].pop(),
        lambda e: e.pop("helper_methods", None),
        lambda e: e.pop("callees", None),
        lambda e: e.pop("callee_chain", None),
        lambda e: e.get("data_origin") and len(e["data_origin"]) > 5 and e["data_origin"].pop(),
        trim_includes,
        trim_flow,
    ]
    for step in steps:
        for entry in reversed(evidence):
            for _ in range(8):
                if size() <= limit:
                    return
                if not step(entry):
                    break


def _embedding_scores(db: Session, project_id: int, query: str, texts: list[str]) -> list[float] | None:
    """Cosine similarity of the query to each text in the project's embedding space; None if unavailable."""
    if not query or not texts:
        return None
    try:
        profile = _embedding_profile_for_project(db, project_id)
        config = {
            "model": profile.model, "provider": profile.provider, "base_url": profile.base_url, "path": profile.path,
            "api_key": profile.api_key, "dimension": profile.dimension, "context_length": profile.context_length,
        }

        async def run() -> list[list[float]]:
            return list(await asyncio.gather(
                *(embed_text(t[:600], is_query=(i == 0), **config) for i, t in enumerate([query, *texts]))))

        # FastMCP calls sync tools on the server's event loop, so the embeddings get a loop of their own.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            vectors = pool.submit(asyncio.run, run()).result(timeout=20)
    except Exception as exc:  # embedding service down, wrong profile, ... -> lexical ranking stays in charge
        logger.info("answer_context embedding relevance unavailable (%s: %s)", type(exc).__name__, str(exc)[:160])
        return None
    head, rest = vectors[0], vectors[1:]
    norm = math.sqrt(sum(x * x for x in head)) or 1.0
    return [sum(a * b for a, b in zip(head, v)) / (norm * (math.sqrt(sum(x * x for x in v)) or 1.0)) for v in rest]


def _embedding_similarities(db: Session, project_id: int, topic: str, texts: dict[str, str]) -> dict[str, float]:
    keys = list(texts)
    scores = _embedding_scores(db, project_id, topic, [texts[k] for k in keys])
    return dict(zip(keys, scores)) if scores is not None else {}


def _rank_by_embedding(db: Session, project_id: int, topic: str, items: list[tuple[float, dict]], key) -> list[tuple[float, dict]]:
    """Blend the lexical score with embedding similarity for the best lexical candidates (top 16)."""
    head = sorted(items, key=lambda row: -row[0])[:12]
    scores = _embedding_scores(db, project_id, topic, [key(item) for _s, item in head])
    if scores is None:
        return items
    blended = [(lex + 8.0 * max(0.0, sim), item) for (lex, item), sim in zip(head, scores)]
    return sorted(blended, key=lambda row: -row[0]) + [row for row in items if row not in head]


def _resolve_chain_target(db: Session, project_id: int, name: str) -> CodeEntity | None:
    rows = db.query(CodeEntity).filter(CodeEntity.project_id == project_id, CodeEntity.qualified_name == name).limit(4).all()
    structural = [e for e in rows if e.type in _STRUCTURAL]
    return (structural or rows or [None])[0]


def build_answer_context(
    db: Session, user: User, project_id: int, *, question: str = "", symbols: list[str] | None = None,
    topic: str = "", max_chars: int = 8000, use_embeddings: bool = True,
) -> dict:
    """Evidence pack for a question: source, callers, callees (two hops), data access and users of the named symbols.

    Shared by the MCP tool and the chat prefetch. `symbols` are names the caller already extracted; without them
    they are taken from the free text."""
    text = " ".join(part for part in (question, topic) if part).strip()
    relevance_query = (topic or question).strip()
    max_chars = max(3000, min(max_chars, 14000))
    if not text or len(text) > 1500:
        raise ToolInputError("invalid query")
    _project(db, user, project_id)
    callers_intent = bool(re.search(
        r"aufrufer|wer ruft|ruft .{0,90}auf|rufen .{0,90}auf|welche (klasse|klassen|programm|programme|methode|methoden|modul|module)|binden .{0,60}ein|einbind|"
        r"verwendet von|verwenden|nutzen|callers?|called by|included? by|who calls|which (classes|programs)",
        text.lower()))
    includes_intent = bool(evidence_blocks.INCLUDES_INTENT.search(text))
    flow_intent = bool(evidence_blocks.FLOW_INTENT.search(text))
    given = [s.strip() for s in (symbols or []) if isinstance(s, str) and 2 < len(s.strip()) <= 160][:8]
    terms = given or _extract_symbols(text)
    resolved: list[tuple[str, CodeEntity, list[CodeEntity], str]] = []
    seen: set[int] = set()
    unresolved: list[str] = []
    ambiguous: list[tuple[str, list[CodeEntity], str]] = []
    for term in terms:
        found, _suggestions, mode = _find_entities(db, user, project_id, term, 6)
        exact = [e for e in found if _symbol_matches(e, term)]
        structural = [e for e in exact if e.type in _STRUCTURAL or e.type == "copybook"] or exact
        if not structural:
            unresolved.append(term)
            continue
        entity, others = _pick_entity(structural)
        if entity is None or entity.id in seen:
            if entity is None:
                ambiguous.append((term, structural, mode))
            continue
        seen.add(entity.id)
        resolved.append((term, entity, others, mode))
    # A bare name that exists in many files (`1000-INITIALIZE`) belongs to the file of the symbols named next to it.
    named_files = {entity.file_path for _t, entity, _o, _m in resolved}
    for term, structural, mode in ambiguous:
        scoped = [e for e in structural if e.file_path in named_files]
        entity, others = _pick_entity(scoped) if scoped else (None, [])
        if entity is None or entity.id in seen:
            if entity is None:
                unresolved.append(term)
            continue
        seen.add(entity.id)
        resolved.append((term, entity, others, mode))
    if not resolved:
        found, suggestions, _mode = _find_entities(db, user, project_id, text[:200], 6)
        return {"project_id": project_id, "question": text, "resolved": [],
                "unresolved_terms": unresolved or terms,
                "candidates": [_compact_entity(e) for e in found[:6]],
                "did_you_mean": suggestions,
                "hint": "No named symbol found. Use search_code with a name from the candidates or search_knowledge for wording."}
    # Method-level references first, then the rest; at most three entities share the budget.
    resolved.sort(key=lambda row: (0 if row[1].type in {"method", "paragraph"} else 1))
    primary = resolved[:3]
    per_entity = max(2500, max_chars // len(primary))
    evidence = []
    for term, entity, others, mode in primary:
        entry = _explain_entity(db, user, project_id, entity, others, mode, term, per_entity, None, None,
                                with_context=True, used_by_limit=40 if callers_intent else 12, compact=True)
        role = role_of(entity.type)
        if role == "container" and includes_intent:
            included = evidence_blocks.includes(db, user, project_id, entity)
            if included:
                entry["includes"] = included
        if role in {"container", "routine"} and flow_intent:
            flow = evidence_blocks.control_flow(db, user, project_id, entity, budget_chars=min(3000, per_entity))
            if flow:
                entry["control_flow"] = flow
        if role == "data":
            origin = evidence_blocks.data_origin(db, user, project_id, entity)
            if origin:
                entry["data_origin"] = origin
                entry["data_origin_notice"] = (
                    "Indexed writes of this data entity, followed backwards through the operands of each write "
                    "(`reads`). Each step is an index fact with its source line; cite it as `cite`. It is not a complete runtime flow."
                )
        if "outline" in entry:
            expanded = []
            child_budget = max(600, min(2200, int(per_entity * 0.62) // 5))
            for item in _relevant_children(
                relevance_query or text, entry["outline"], 4,
                sims=(lambda items: _embedding_similarities(
                    db, project_id, relevance_query, {i["symbol"]: f"{i['symbol']} {i.get('facts', '')}" for i in items}
                )) if use_embeddings and relevance_query else None,
            ):
                child = db.query(CodeEntity).filter(
                    CodeEntity.project_id == project_id, CodeEntity.file_path == entity.file_path,
                    CodeEntity.qualified_name == item["symbol"]).first()
                if child is None:
                    continue
                part = _explain_entity(db, user, project_id, child, [], "exact", item["symbol"], child_budget, None, None, with_context=False, compact=True)
                if part.get("source"):
                    expanded.append({"symbol": item["symbol"], "lines": item["lines"], "facts": item.get("facts"),
                                     "source": part["source"]})
            shown = {x["symbol"] for x in expanded}
            entry["outline"] = [dict(i, facts=i["facts"][:70]) if i.get("facts") else i
                                for i in entry["outline"] if i["symbol"] not in shown and i.get("type") not in _CHILD_SKIP][:6]
            if expanded:
                entry["expanded"] = expanded
            entry["notice"] = "Outline of the whole unit plus the source of the parts that match the question best."
        elif entry.get("callees"):
            full_callees = entry["callees"]
            entry["callees"] = [f"{c['to'].split('(', 1)[0].rsplit('.', 1)[-1]} (Zeile {c.get('line')})" for c in full_callees[:12] if c.get("to")]
            # Methods often delegate to a helper in the same class: read the most relevant one as well.
            q_stems = _question_stems(text)
            same_file = [c for c in full_callees if c.get("location", "").startswith(f"{entity.file_path}:") and c.get("to")]
            candidates = []
            for c in same_file[:8]:
                child = db.query(CodeEntity).filter(
                    CodeEntity.project_id == project_id, CodeEntity.file_path == entity.file_path,
                    CodeEntity.qualified_name == c["to"]).first()
                if child is None or child.id == entity.id:
                    continue
                tail = re.split(r"[.#]", c["to"].split("(", 1)[0])[-1].lower()
                relevance = len(q_stems & {t[:5] for t in re.findall(r"[a-z0-9]{3,}", tail)}) * 2
                size = (child.end_line or 0) - (child.start_line or 0)
                candidates.append((relevance + min(4, size // 25), {"child": child, "name": c["to"]}))
            if use_embeddings and relevance_query and len(candidates) > 1:
                candidates = _rank_by_embedding(db, project_id, relevance_query, candidates, lambda i: i["name"])
            helpers = []
            for _score, item in sorted(candidates, key=lambda row: -row[0])[:2]:
                child, name = item["child"], item["name"]
                if any(h["symbol"] == name for h in helpers):
                    continue
                part = _explain_entity(db, user, project_id, child, [], "exact", name, 4200, None, None, with_context=False, compact=True)
                if part.get("source"):
                    helpers.append({"symbol": name, "lines": f"{child.start_line}-{child.end_line}", "source": part["source"]})
            if helpers:
                entry["helper_methods"] = helpers
            # Second hop: the callees that are not helpers already read, with their own callees.
            taken = {h["symbol"] for h in helpers} | {entity.qualified_name}
            chain_candidates, tried = [], set()
            for c in full_callees:
                name = c.get("to")
                if not name or name in taken or name in tried or len(tried) >= 10:
                    continue
                tried.add(name)
                target = _resolve_chain_target(db, project_id, name)
                size = ((target.end_line or 0) - (target.start_line or 0)) if target is not None else 0
                if target is None or target.id == entity.id or size < 4:
                    continue  # unresolved, recursive or a trivial accessor
                tail = re.split(r"[.#]", name.split("(", 1)[0])[-1].lower()
                relevance = len(q_stems & {t[:5] for t in re.findall(r"[a-z0-9]{3,}", tail)}) * 2
                chain_candidates.append((relevance + min(4, size // 25), {"target": target, "name": name, "line": c.get("line")}))
            if use_embeddings and relevance_query and len(chain_candidates) > 1:
                chain_candidates = _rank_by_embedding(db, project_id, relevance_query, chain_candidates, lambda i: i["name"])
            chain = []
            for _score, item in sorted(chain_candidates, key=lambda row: -row[0])[:2]:
                target, name = item["target"], item["name"]
                part = _explain_entity(db, user, project_id, target, [], "exact", name, 2600, None, None, with_context=False, compact=True)
                if not part.get("source"):
                    continue
                try:
                    onward = _flow_summary(_call_flow_page(db, user, project_id, target.id, hops=1, direction="outgoing",
                                                           scope="execution", page_size=10, cursor=None, include_source=False), "outgoing", 10)
                except (ValueError, HTTPException):
                    onward = []
                chain.append({"symbol": name, "lines": f"{target.start_line}-{target.end_line}", "file": target.file_path,
                              "called_at_line": item["line"], "source": part["source"],
                              "calls": [f"{o['to'].split('(', 1)[0].rsplit('.', 1)[-1]} (Zeile {o.get('line')})" for o in onward if o.get("to")]})
            if chain:
                entry["callee_chain"] = chain
        if callers_intent:
            sites = []
            for caller in (entry.get("callers") or [])[:2]:
                caller_entity = db.query(CodeEntity).filter(
                    CodeEntity.project_id == project_id, CodeEntity.qualified_name == caller.get("from")).first()
                if caller_entity is not None and caller.get("line"):
                    site = _site_excerpt(db, user, caller_entity, int(caller["line"]), 16)
                    if site:
                        site["caller"] = caller.get("from")
                        sites.append(site)
            if sites:
                entry["call_sites"] = sites
        evidence.append(entry)
    _fit_evidence(evidence, max_chars - 600)
    return {
        "project_id": project_id,
        "resolved": [{"symbol": e.qualified_name, "type": e.type, "location": f"{e.file_path}:{e.start_line}-{e.end_line}"}
                     for _t, e, _o, _m in primary],
        "unresolved_terms": unresolved, "evidence": evidence,
        "notice": "Evidence assembled by the server from the index. Cite every fact as `path/file.ext:line` in backticks, "
                  "copying the `cite` fields where present; never write 'line N of file'. Call explain_symbol for any other symbol.",
    }


@mcp.tool(annotations=READ_ONLY)
def answer_context(
    ctx: Context,
    project_id: int,
    symbols: Annotated[list[str] | None, Field(description="Code names from the question (programs, classes, methods, paragraphs).")] = None,
    topic: Annotated[str | None, Field(description="Few words on what to find out, e.g. 'interest calculation'.")] = None,
    question: Annotated[str | None, Field(description="Alternative to symbols/topic: the user's question, verbatim.")] = None,
    max_chars: Annotated[int, Field(description="Evidence budget, 3000-14000.")] = 8000,
) -> dict:
    """FIRST CHOICE for any question about code: pass the symbol names and a short topic. Returns, in one call, the source with line numbers, callers, callees (two hops), data access and users of each symbol. Answer from it and cite file:line."""
    max_chars = max(3000, min(max_chars, 14000))
    with _tool_context(ctx, "answer_context", project_id, {"max_chars": max_chars}) as (db, user):
        response = build_answer_context(db, user, project_id, question=(question or "").strip(), symbols=symbols,
                                        topic=(topic or "").strip(), max_chars=max_chars)
        _capture_mcp_result(ctx, db, project_id, response)
        return response


@mcp.tool(annotations=READ_ONLY)
def explain_symbol(
    ctx: Context,
    project_id: int,
    symbol: str,
    max_chars: Annotated[int, Field(description="Budget 1500-12000.")] = 7000,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict:
    """Everything about ONE named class, method, program or paragraph in one call: source with line numbers, callers, callees, data access. Accepts Klasse.methode, Klasse#methode, PROGRAM.PARAGRAPH. A large unit returns an outline; call again with an outline symbol or start_line/end_line."""
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
        response = _explain_entity(db, user, project_id, entity, others, mode, symbol, max_chars, start_line, end_line)
        _capture_mcp_result(ctx, db, project_id, response)
        return response


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

    Accepts ``Klasse.methode`` and ``Klasse#methode`` alike, several alternatives separated by ``|``,
    and short phrases such as ``authenticate AuthDataAccessor``. An empty result lists similar names.
    To understand a symbol use ``explain_symbol`` (source, callers, callees and data access in one call).
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
        # Parameters and locals only clutter a symbol search; keep them when they are the exact match.
        entities = [e for e in entities if e.type not in _NOISE_TYPES
                    or any((e.name or "").casefold() == a.strip().casefold() for a in alternatives)]
        total = len(entities)
        entities = entities[:limit]
        visible = []
        for entity in entities:
            item = {"id": entity.id, "qualified_name": entity.qualified_name, "type": entity.type,
                    "location": f"{entity.file_path}:{entity.start_line}-{entity.end_line}"}
            signature = (entity.meta_json or {}).get("signature")
            if signature:
                item["signature"] = signature
            exact = any(_symbol_matches(entity, alternative) for alternative in alternatives)
            # Source only where it can be cited directly: the best exact match.
            wants_source = include_source and exact and not any("source_excerpt" in v for v in visible)
            if wants_source and entity.type in _STRUCTURAL | {"field", "compilation_unit", "data_item"}:
                result = entity_api.get_entity(entity_id=entity.id, project_id=project_id, db=db, user=user)
                definition = result.get("definition")
                if definition:
                    excerpt, clipped = _bounded(definition.get("content"), 2400)
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
        for item in visible[:1]:
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
def research_project(ctx: Context, project_id: int, query: str, limit: int = 8, hops: Annotated[int, Field(description="Depth 0-3, larger clamped to 3.")] = 2) -> dict:
    """Locate symbols and, for one exact candidate, return its call-flow GRAPH (structure only, no source code).

    To read the code, callers, callees and data access of a symbol use ``explain_symbol`` instead.
    """
    query = query.strip()
    limit = max(1, min(limit, 12))
    hops = max(0, min(hops, 3))
    with _tool_context(ctx, "research_project", project_id, {"limit": limit, "hops": hops}) as (db, user):
        if not query or len(query) > 200:
            raise ValueError("invalid query")
        _project(db, user, project_id)
        terms = _research_terms(query)
        prose_query: str | None = None
        if len(terms) == 1 and re.search(r"\s", terms[0]):
            # Freitext mit Symbolen: die benannten Symbole auflösen und die Frage selbst weiter an die Inhaltssuche
            # verweisen. Löst keines auf, bleibt es bei der Freitext-Antwort (no_exact_match samt Folgeaktionen).
            resolved_mentions = []
            for mention in _mentioned_symbols(terms[0]):
                mentioned, _suggestions, _mode = _find_entities(db, user, project_id, mention, limit)
                if any(_symbol_matches(entity, mention) for entity in mentioned):
                    resolved_mentions.append(mention)
            if resolved_mentions:
                prose_query, terms = terms[0], resolved_mentions
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
            # Parameter und lokale Variablen einer Methode tragen deren Namen im Qualified Name; sie machen
            # einen sonst eindeutigen Treffer nicht mehrdeutig.
            exact = [item for item in exact if item["type"] not in _NOISE_TYPES] or exact
            if "/" in term:
                file_programs = [item for item in exact if item["type"] in {"program", "cobol_program", "compilation_unit"}]
                if file_programs:
                    exact = file_programs
            overloads = []
            if not exact and _query_signature(term) is not None:
                # Name stimmt, Signatur nicht: vorhandene Überladungen zeigen statt eine fremde Signatur als exakt auszugeben.
                overloads = [serialize(entity) for entity in by_id.values()
                             if _symbol_name_matches(entity, term) and _entity_signature(entity) is not None
                             and entity.type not in _NOISE_TYPES]
            match = {
                "query": term,
                "resolution": "unique_exact_match" if len(exact) == 1 else (
                    "ambiguous" if len(exact) > 1 else ("signature_mismatch" if overloads else "no_exact_match")
                ),
                "candidates": (exact or overloads)[:limit],
                "candidate_count": len(exact or overloads),
            }
            if overloads:
                match["notice"] = "Keine Überladung mit dieser Signatur im Index; die vorhandenen Überladungen stehen in `candidates`."
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
        if prose_query is not None:
            response["query_interpretation"] = "symbols_in_text"
            response["original_query"] = prose_query
            response["follow_up_actions"] = [*(response.get("follow_up_actions") or []), {
                "tool": "search_knowledge",
                "arguments": {"project_id": project_id, "query": prose_query, "limit": 5},
                "reason": "The question is prose; the named symbols were resolved above, search project knowledge for the wording itself.",
            }]
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
    for label in ("calls", "performs", "cics", "datasets", "io", "computes", "sets", "msgs"):
        literal = label in {"sets", "msgs", "computes"}
        names = [name if literal else name.split("(", 1)[0][-48:] for name in (buckets.get(label) or [])]
        if names:
            parts.append(f"{label} {', '.join(names[:3 if literal else 5])}")
    return "; ".join(parts)[:320]


_STRING_LITERAL = re.compile(r"\"([^\"\n]{8,80})\"|'([^'\n]{8,80})'")
_NOISE_VARIABLE = re.compile(r"RESULT|IO-STATUS|ABCODE|TIMING|TWO-BYTES|^DB2-REST|-BINARY$|-IDX$|-SUB$", re.I)
_COBOL_ARITHMETIC = re.compile(r"\b(?:COMPUTE\s+([A-Z][A-Z0-9-]*)|(?:ADD|SUBTRACT)\s+[A-Z0-9][A-Z0-9-]*\s+(?:TO|FROM)\s+([A-Z][A-Z0-9-]*))", re.I)
_COBOL_SET_CODE = re.compile(r"\bMOVE\s+(?:'([A-Za-z0-9]{1,8})'|\"([A-Za-z0-9]{1,8})\"|(\d{1,4}))\s+TO\s+([A-Z0-9][A-Z0-9-]*)", re.I)


def _literal_facts(db: Session, entity: CodeEntity, children: list[CodeEntity]) -> dict[int, dict[str, list[str]]]:
    """Message texts and assigned status codes inside each child, read from the indexed source lines."""
    if not children:
        return {}
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.project_id == entity.project_id, DocumentChunk.source_id == entity.source_id,
        DocumentChunk.file_path == entity.file_path, DocumentChunk.start_line <= entity.end_line,
        DocumentChunk.end_line >= entity.start_line,
    ).order_by(DocumentChunk.start_line).limit(120).all()
    lines: dict[int, str] = {}
    for chunk in chunks:
        for offset, text in enumerate(chunk.content.splitlines()):
            lines.setdefault(chunk.start_line + offset, text)
    result: dict[int, dict[str, list[str]]] = {}
    for child in children:
        found: dict[str, list[str]] = {}
        for number in range(child.start_line or 0, min(child.end_line or 0, (child.start_line or 0) + 400) + 1):
            text = lines.get(number)
            if not text or text.lstrip().startswith(("*", "//", "/*")) or (len(text) > 6 and text[6] == "*"):
                continue
            for match in _COBOL_ARITHMETIC.finditer(text):
                target = (match.group(1) or match.group(2)).upper()
                if not _NOISE_VARIABLE.search(target) and target not in found.setdefault("computes", []):
                    found["computes"].append(target)
            for match in _COBOL_SET_CODE.finditer(text):
                if _NOISE_VARIABLE.search(match.group(4)):
                    continue
                code = match.group(1) or match.group(2) or match.group(3)
                item = f"{match.group(4)}={code}"
                if item not in found.setdefault("sets", []):
                    found["sets"].append(item)
            for match in _STRING_LITERAL.finditer(text):
                literal = (match.group(1) or match.group(2)).strip().replace("(", "[").replace(")", "]")
                if re.search(r"[A-Za-z]{3}", literal) and " " in literal and literal not in found.setdefault("msgs", []):
                    found["msgs"].append(f'"{literal[:44]}"')
        if found:
            result[child.id] = found
    return result


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
    literals = _literal_facts(db, entity, children)
    for child in children:
        buckets: dict[str, list[str]] = dict(literals.get(child.id, {}))
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
        CodeEdge.type.in_(["READS", "WRITES", "USES_DATASET", "ASSIGNED_DATASET"]),
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
        if meta.get("derived_by") == "jcl_dd_assign" and "ddname" not in group:
            # O-147: Datei des Programms ↔ Dataset aus dem JCL-DD gleichen Namens (nur `possible`).
            group["ddname"] = meta.get("ddname")
            group["via_jcl"] = f"{meta.get('jcl_file_path')}:{meta.get('jcl_start_line')}"
            group["certainty"] = "possible"
    order = {"WRITES": 0, "USES_DATASET": 1, "ASSIGNED_DATASET": 1, "READS": 2}
    return sorted(groups.values(), key=lambda g: (0 if g.get("file_io") else 1, order.get(g["access"], 3), g["lines"][0] or 0))[:limit]


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
    symbol: Annotated[str | None, Field(description="Qualified name instead of entity_id.")] = None,
) -> dict:
    """Read one indexed entity (entity_id or symbol) with line-attributed source, paged."""
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
    include_tests: bool = True,
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
        # Ältere Cursor kennen include_tests nicht; sie gelten als include_tests=True.
        if cursor_data.get("include_tests", True) != include_tests:
            raise ValueError("cursor does not match this call-flow query")
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
        include_tests=include_tests,
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
            "include_tests": include_tests, "offset": next_offset,
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
                "include_tests": include_tests,
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
    hops: Annotated[int, Field(description="Depth 0-3, larger clamped to 3.")] = 2,
    direction: Literal["outgoing", "incoming", "both"] = "outgoing",
    scope: Literal["execution", "dependencies", "all"] = "execution",
    page_size: Annotated[int, Field(description="Edges per page 1-15, larger clamped to 15.")] = 10,
    cursor: Annotated[str | None, Field(description="next_cursor of the previous page, unchanged.")] = None,
    include_source: bool = True,
    include_tests: Annotated[bool, Field(
        description="false hides edges from/to test code (src/test, *Test.java) so callers and impact show production code only."
    )] = True,
) -> dict:
    """Trace executable calls or resource/data dependencies in a project.

    ``scope`` selects ``execution`` (CALL/PERFORM/etc.), ``dependencies``
    (COPY/import/resource/data edges), or ``all``. ``direction`` is outgoing,
    incoming, or both; outgoing and both resolve a COBOL program or Java class to
    its entry paragraph or method (``both`` additionally returns the callers of the
    program or class itself). Continue a large result with the returned ``next_cursor``
    and the same root, hops, direction, and scope.
    """
    hops = max(0, min(hops, 3))
    page_size = max(1, min(page_size, 15))
    with _tool_context(ctx, "get_call_flow", project_id, {
        "entity_id": entity_id, "hops": hops, "scope": scope,
        "direction": direction, "page_size": page_size, "cursor": cursor,
        "include_source": include_source, "include_tests": include_tests,
    }) as (db, user):
        response = _call_flow_page(
            db, user, project_id, entity_id, hops=hops, direction=direction, scope=scope,
            page_size=page_size, cursor=cursor, include_source=include_source,
            include_tests=include_tests,
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


def _slim_schema(node) -> None:
    """Drop pydantic's per-property titles: they only add tokens to every tool listing."""
    if isinstance(node, dict):
        if isinstance(node.get("title"), str):
            node.pop("title")
        for value in node.values():
            _slim_schema(value)
    elif isinstance(node, list):
        for value in node:
            _slim_schema(value)



for _tool in mcp._tool_manager.list_tools():
    _slim_schema(_tool.parameters)


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
