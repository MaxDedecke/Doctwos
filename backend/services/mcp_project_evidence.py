"""Read-only MCP project evidence, sharing HTTP validation and chat representations."""

import httpx
from fastapi import HTTPException
from mcp.types import ToolAnnotations
from mcp.server.fastmcp import Context
from typing import Annotated, Literal
from pydantic import Field

from api.change_packages import get_change_package
from doctus_models.database import User
from services.code_symbols import _project
from services.project_evidence import project_evidence
from services.agent_tool_results import _compact_change_package_for_agent


async def knowledge_result(
    db,
    user,
    project_id,
    query,
    limit,
    *,
    embedding_profile,
    search_chunks,
    lexical_chunks,
    chunk_visible,
):
    if not query or len(query) > 500:
        raise ValueError("invalid query")
    _project(db, user, project_id)
    user_id = user.id
    mode = "semantic"
    try:
        profile = embedding_profile(db, project_id)
        config = {
            "embedding_model": profile.model,
            "embedding_provider": profile.provider,
            "embedding_base_url": profile.base_url,
            "embedding_path": profile.path,
            "embedding_api_key": profile.api_key,
            "embedding_dimension": profile.dimension,
            "embedding_context_length": profile.context_length,
        }
        db.close()
        chunks = await search_chunks(db, project_id, query, limit=limit + 1, **config)
    except (httpx.HTTPError, ValueError, LookupError, OSError):
        mode = "lexical_fallback"
        chunks = lexical_chunks(db, project_id, query, limit + 1)
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if user is None:
        raise HTTPException(status_code=401)
    _project(db, user, project_id)
    results = []
    for chunk in chunks[:limit]:
        if not chunk_visible(db, user, project_id, chunk):
            continue
        content = (chunk.content or "")[:1200]
        results.append(
            {
                "chunk_id": chunk.id,
                "project_id": project_id,
                "source_id": chunk.source_id,
                "file_path": chunk.file_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content": content,
                "content_truncated": len(chunk.content or "") > 1200,
            }
        )
    return {
        "results": results,
        "truncated": len(chunks) > limit or len(results) < min(len(chunks), limit),
        "limit_applied": limit,
        "retrieval_mode": mode,
        "notice": (
            "Semantic similarity is a retrieval hint, not a verified conclusion."
            if mode == "semantic"
            else "The embedding service is unavailable; results come from a keyword match, "
            "not semantic similarity. Use search_code or get_code_entity for source-backed evidence."
        ),
        **project_evidence(db, user, project_id, query, nodes=results),
    }


def register_change_package(mcp, tool_context, capture_result):
    @mcp.tool(
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
    )
    def inspect_change_package(
        ctx: Context,
        project_id: int,
        entity_id: Annotated[int | None, Field(ge=1)] = None,
        file_path: Annotated[str | None, Field(min_length=1, max_length=1000)] = None,
        source_id: Annotated[int | None, Field(ge=1)] = None,
        base_ref: Annotated[str | None, Field(min_length=1, max_length=256)] = None,
        head_ref: Annotated[str | None, Field(min_length=1, max_length=256)] = None,
        direction: Literal["incoming", "outgoing", "both"] = "incoming",
        hops: Annotated[int, Field(ge=0, le=3)] = 2,
        limit: Annotated[int, Field(ge=10, le=80)] = 40,
    ) -> dict:
        """Inspect a change with the web view's findings, commit-bound CI runs, impact, links, tests and owners.
        Supply an entity/file, or base_ref + head_ref and source_id. Findings retain review/version status;
        drafts/stale findings are not approved facts. CI outcomes do not establish coverage or merge approval."""
        with tool_context(
            ctx, "inspect_change_package", project_id, {"hops": hops, "limit": limit}
        ) as (db, user):
            result = get_change_package(
                project_id,
                entity_id,
                file_path,
                source_id,
                base_ref,
                head_ref,
                direction,
                hops,
                limit,
                db,
                user,
            )
            result = _compact_change_package_for_agent(result)
            capture_result(ctx, db, project_id, result)
            return result

    return inspect_change_package
