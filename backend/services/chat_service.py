"""Testable application services used by the SSE chat endpoint.

The API router deliberately owns HTTP concerns (authorization, session selection and
``StreamingResponse``).  This module owns the chat-specific transformations which do
not need FastAPI and can therefore be exercised without running the route.
"""

import json
import logging
import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

import core.config as cfg
from models.database import ChatMessage, DocumentChunk, KnowledgeSource, Project, User
from services.graph_retrieval import expand_chunks_with_graph

from core.projects import (
    build_document_chunk_code_gate,
    get_globally_exposed_project_ids,
    get_visible_project_ids,
    is_document_chunk_code_visible_in_context,
    resolve_repository_id,
)
from core.teams import get_visible_team_ids

logger = logging.getLogger(__name__)


_PAGE_QUERY_RE = re.compile(r"(?:seite|page|s\.)\s*(\d+)", re.IGNORECASE)
_SECTION_NUMBER_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){1,4}\b")
_SECTION_MATCH_SCAN_LIMIT = 3000


@dataclass
class ChatRetrieval:
    """All context produced before an LLM provider starts streaming."""

    results: list[DocumentChunk]
    pinned_chunks: list[DocumentChunk]
    context: str
    pinned_context: str
    prompt: str
    resolved_repo_id: Optional[int]
    focused_source_id: Optional[int]
    multi_project_names: list[str]


def hybrid_chunk_search(
    base_query, query_embedding: list, query_text: str, limit: int
) -> list[DocumentChunk]:
    """Search exact page/section references before topping up with vector results."""
    picked: list[DocumentChunk] = []
    picked_ids = set()

    def add_all(rows):
        for row in rows:
            if row.id not in picked_ids:
                picked_ids.add(row.id)
                picked.append(row)

    page_match = _PAGE_QUERY_RE.search(query_text)
    if page_match:
        page_no = int(page_match.group(1))
        add_all(
            base_query.filter(DocumentChunk.metadata_json["page"].as_integer() == page_no)
            .limit(limit)
            .all()
        )

    if len(picked) < limit:
        section_match = _SECTION_NUMBER_RE.search(query_text)
        if section_match:
            needle = section_match.group(0)
            candidates = base_query.limit(_SECTION_MATCH_SCAN_LIMIT).all()
            matches = [chunk for chunk in candidates if needle in (chunk.content or "")]
            add_all(matches[: limit - len(picked)])

    if len(picked) < limit:
        add_all(
            base_query.order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
            .limit(limit - len(picked))
            .all()
        )
    return picked


def gate_graph_neighbors(
    db: Session, chunks: list[DocumentChunk], requesting_project_id: Optional[int]
) -> list[DocumentChunk]:
    """Apply the project code-visibility gate after graph expansion."""
    return [
        chunk
        for chunk in chunks
        if is_document_chunk_code_visible_in_context(chunk, requesting_project_id, db)
    ]


def _format_chunk_context(chunk: DocumentChunk, label: str) -> str:
    """Render one retrieved chunk as explicitly untrusted model context."""
    return (
        f'<untrusted_source path="{chunk.file_path}">\n'
        f"{label}: {chunk_header(chunk)}\n"
        f"{chunk.content}\n"
        "</untrusted_source>"
    )


async def retrieve_chat_context(
    *,
    db: Session,
    user: User,
    project_id: Optional[int],
    source_id: Optional[int],
    pinned_source_id: Optional[int],
    pinned_file: Optional[str],
    pinned_line: Optional[int],
    pinned_label: Optional[str],
    focused_context: Optional[str],
    message: str,
) -> ChatRetrieval:
    """Embed a chat question and assemble its permission-scoped context.

    Retrieval, graph expansion and pin fallback are kept together because their
    visibility rules must be applied consistently before prompt construction.
    Provider calls do not belong here; this function returns only prepared data.
    """
    results: list[DocumentChunk] = []
    context = ""
    multi_project_names: list[str] = []
    resolved_repo_id = resolve_repository_id(project_id, db) if project_id else None
    focused_source_id = pinned_source_id or source_id or resolved_repo_id

    if pinned_source_id:
        focused_source = (
            db.query(KnowledgeSource)
            .filter(KnowledgeSource.id == pinned_source_id, KnowledgeSource.type == "Git")
            .first()
        )
        if focused_source and (project_id is None or focused_source.project_id == project_id):
            resolved_repo_id = focused_source.id

    team_ids = get_visible_team_ids(user, db)
    global_query = db.query(KnowledgeSource.id).filter(KnowledgeSource.project_id.is_(None))
    if team_ids is not None:
        global_query = global_query.filter(KnowledgeSource.team_id.in_(team_ids))
    global_source_ids = [row.id for row in global_query.all()]

    try:
        query_text = message
        if cfg.OLLAMA_EMBED_MODEL.startswith("nomic-embed-text") and not query_text.startswith(
            "search_query:"
        ):
            query_text = f"search_query: {query_text}"
        async with httpx.AsyncClient(timeout=60.0) as embed_client:
            response = await embed_client.post(
                f"{cfg.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": cfg.OLLAMA_EMBED_MODEL, "prompt": query_text},
            )
            query_embedding = response.json()["embedding"]

        if source_id:
            base_query = db.query(DocumentChunk).filter(DocumentChunk.source_id == source_id)
            results = hybrid_chunk_search(base_query, query_embedding, query_text, 4)
            results = gate_graph_neighbors(db, expand_chunks_with_graph(db, results), project_id)
            context = "\n\n".join(_format_chunk_context(row, "File") for row in results)
        elif project_id:
            project_source_ids = [
                row.id
                for row in db.query(KnowledgeSource.id)
                .filter(KnowledgeSource.project_id == project_id)
                .all()
            ]
            repo_query = db.query(DocumentChunk).filter(
                DocumentChunk.project_id == project_id,
                DocumentChunk.source_id.is_(None),
            )
            repo_results = hybrid_chunk_search(repo_query, query_embedding, query_text, 4)
            repo_results = gate_graph_neighbors(
                db, expand_chunks_with_graph(db, repo_results), project_id
            )

            project_source_results: list[DocumentChunk] = []
            if project_source_ids:
                source_query = db.query(DocumentChunk).filter(
                    DocumentChunk.source_id.in_(project_source_ids)
                )
                project_source_results = hybrid_chunk_search(
                    source_query, query_embedding, query_text, 4
                )
                project_source_results = gate_graph_neighbors(
                    db, expand_chunks_with_graph(db, project_source_results), project_id
                )

            global_results: list[DocumentChunk] = []
            if global_source_ids:
                global_query = db.query(DocumentChunk).filter(
                    DocumentChunk.source_id.in_(global_source_ids)
                )
                global_results = hybrid_chunk_search(global_query, query_embedding, query_text, 2)
                global_results = gate_graph_neighbors(
                    db, expand_chunks_with_graph(db, global_results), project_id
                )

            results = repo_results + project_source_results + global_results
            context_parts = []
            if repo_results:
                context_parts.append("--- IN-SCOPE REPOSITORY FILES ---")
                context_parts.extend(_format_chunk_context(row, "File") for row in repo_results)
            if project_source_results:
                context_parts.append("--- IN-SCOPE PROJECT KNOWLEDGE SOURCES ---")
                context_parts.extend(
                    _format_chunk_context(row, "Source Document") for row in project_source_results
                )
            if global_results:
                context_parts.append("--- OUT-OF-SCOPE GLOBAL KNOWLEDGE SOURCES ---")
                context_parts.extend(
                    _format_chunk_context(row, "Source Document") for row in global_results
                )
            context = "\n\n".join(context_parts)
        else:
            visible_project_ids = get_visible_project_ids(user, db)
            exposed_project_ids = get_globally_exposed_project_ids(db)
            if visible_project_ids is not None:
                exposed_project_ids = [
                    project_id
                    for project_id in exposed_project_ids
                    if project_id in visible_project_ids
                ]
            elif team_ids is not None:
                team_project_ids = {
                    row[0]
                    for row in db.query(Project.id).filter(Project.team_id.in_(team_ids)).all()
                }
                exposed_project_ids = [
                    project_id
                    for project_id in exposed_project_ids
                    if project_id in team_project_ids
                ]
            code_gate = build_document_chunk_code_gate(db, exposed_project_ids)

            scope_filters = []
            if visible_project_ids is None:
                base_query = db.query(DocumentChunk)
            else:
                if visible_project_ids:
                    scope_filters.append(DocumentChunk.project_id.in_(visible_project_ids))
                if global_source_ids:
                    scope_filters.append(DocumentChunk.source_id.in_(global_source_ids))
                base_query = (
                    db.query(DocumentChunk).filter(or_(*scope_filters)) if scope_filters else None
                )
            if base_query is not None:
                if code_gate is not None:
                    base_query = base_query.filter(code_gate)
                results = hybrid_chunk_search(base_query, query_embedding, query_text, 6)
                results = gate_graph_neighbors(db, expand_chunks_with_graph(db, results), None)

            result_project_ids = sorted(
                {row.project_id for row in results if row.project_id is not None}
            )
            if result_project_ids:
                projects_by_id = {
                    project.id: project.name
                    for project in db.query(Project)
                    .filter(Project.id.in_(result_project_ids))
                    .all()
                }
                multi_project_names = sorted(set(projects_by_id.values()))
            else:
                projects_by_id = {}
            context = "\n\n".join(
                _format_chunk_context(
                    row,
                    f"[{'Projekt: ' + projects_by_id[row.project_id] if row.project_id in projects_by_id else 'Global'}] File",
                )
                for row in results
            )
    except Exception as exc:
        logger.error("Fehler beim Kontext-Retrieval: %s", exc)
        query_text = message

    pinned_chunks = (
        find_pinned_chunks(db, project_id, focused_source_id, pinned_file, pinned_line)
        if pinned_file
        else []
    )
    pinned_context = build_pinned_context(
        pinned_file=pinned_file,
        pinned_line=pinned_line,
        pinned_label=pinned_label,
        pinned_context=focused_context,
        pinned_chunks=pinned_chunks,
        repository_id=resolved_repo_id,
    )
    prompt = build_chat_prompt(
        context=context,
        pinned_context=pinned_context,
        message=message,
        pinned_file=pinned_file,
        multi_project_names=multi_project_names,
    )
    return ChatRetrieval(
        results=results,
        pinned_chunks=pinned_chunks,
        context=context,
        pinned_context=pinned_context,
        prompt=prompt,
        resolved_repo_id=resolved_repo_id,
        focused_source_id=focused_source_id,
        multi_project_names=multi_project_names,
    )


async def stream_standard_rag_events(
    *,
    provider: str,
    model: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
    temperature: Optional[float],
    system_prompt: str,
    history: list[ChatMessage],
    prompt: str,
) -> AsyncIterator[dict[str, Any]]:
    """Stream a non-agent provider response as normalized chat events.

    The router only has to serialize the returned events as SSE and collect the
    final answer. Provider-specific payloads and response parsing stay testable
    without constructing a FastAPI response.
    """
    answer = ""
    try:
        if provider in ("openai", "ollama"):
            is_ollama = provider == "ollama"
            if is_ollama:
                url = f"{cfg.OLLAMA_BASE_URL}/v1/chat/completions"
                headers = {"Content-Type": "application/json"}
                model_to_use = cfg.resolve_ollama_model(model)
                payload = {
                    "model": model_to_use,
                    "messages": [{"role": "system", "content": system_prompt}],
                    "temperature": temperature if temperature is not None else 0.7,
                    "stream": True,
                }
            else:
                base = (base_url or "https://api.openai.com/v1").rstrip("/")
                url = base if "/chat/completions" in base else f"{base}/chat/completions"
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                model_to_use = model or "gpt-4o"
                payload = {
                    "model": model_to_use,
                    "messages": [{"role": "system", "content": system_prompt}],
                    "stream": True,
                }
                if cfg.openai_model_supports_custom_temperature(model_to_use):
                    payload["temperature"] = temperature if temperature is not None else 0.7

            payload["messages"].extend(
                {"role": message.role, "content": message.content} for message in history
            )
            payload["messages"].append({"role": "user", "content": prompt})

            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip() or not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            if not chunk.get("choices"):
                                continue
                            content = chunk["choices"][0].get("delta", {}).get("content")
                            if content:
                                answer += content
                                yield {"type": "content_chunk", "content": content}
                        except Exception as exc:
                            logger.error("Fehler beim Parsen des Stream-Chunks: %s", exc)

        elif provider == "gemini":
            model_name = model or "gemini-1.5-flash"
            contents = [
                {
                    "role": "user" if message.role == "user" else "model",
                    "parts": [{"text": message.content}],
                }
                for message in history
            ]
            contents.append({"role": "user", "parts": [{"text": prompt}]})
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": temperature if temperature is not None else 0.7
                },
            }
            if system_prompt:
                payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
            full_url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:generateContent?key={api_key or ''}"
            )
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    full_url, json=payload, headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                answer = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            yield {"type": "content_chunk", "content": answer}

        elif provider == "anthropic":
            model_name = model or "claude-3-5-sonnet-20241022"
            messages = [{"role": message.role, "content": message.content} for message in history]
            messages.append({"role": "user", "content": prompt})
            payload = {
                "model": model_name,
                "max_tokens": 4096,
                "messages": messages,
                "temperature": temperature if temperature is not None else 0.7,
            }
            if system_prompt:
                payload["system"] = system_prompt
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": api_key or "",
                        "anthropic-version": "2023-06-01",
                    },
                )
                response.raise_for_status()
                answer = response.json()["content"][0]["text"]
            yield {"type": "content_chunk", "content": answer}

        yield {"type": "turn_completed", "has_tool_calls": False}
        yield {"type": "answer", "content": answer, "agent_steps": []}
    except Exception as exc:
        error_detail = f"Fehler bei der Kommunikation mit dem LLM-Provider ({provider}): {exc}"
        logger.error(error_detail)
        yield {"type": "error", "error": error_detail}


async def stream_agent_events(
    *,
    provider: str,
    model_name: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
    system_prompt: str,
    prompt: str,
    temperature: Optional[float],
    repository_id: Optional[int],
    db: Session,
    mcp_clients: list,
    ollama_base_url: str,
    history: list[dict[str, Any]],
    project_id: Optional[int],
    user_id: int,
    session_id: int,
    user_message_id: int,
) -> AsyncIterator[dict]:
    """Yield the agent tool-loop events for one chat turn.

    The router serializes these events as SSE. Keeping the loop here makes its
    tool/audit contract reusable and independently testable without FastAPI.
    """
    from agent import run_agent_loop

    async for event in run_agent_loop(
        provider=provider,
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        system_prompt=system_prompt,
        prompt=prompt,
        temperature=temperature,
        repo_id=repository_id,
        db_session=db,
        mcp_clients=mcp_clients,
        ollama_base_url=ollama_base_url,
        chat_history=history,
        project_id=project_id,
        audit_user_id=user_id,
        audit_chat_session_id=session_id,
        audit_chat_message_id=user_message_id,
    ):
        yield event


def find_pinned_chunks(
    db: Session,
    project_id: Optional[int],
    source_id: Optional[int],
    file_path: str,
    line: Optional[int],
) -> list[DocumentChunk]:
    """Return up to three indexed chunks covering a focused file and line."""
    query = db.query(DocumentChunk).filter(DocumentChunk.file_path == file_path)
    if project_id is not None:
        query = query.filter(DocumentChunk.project_id == project_id)
    if source_id is not None:
        query = query.filter(DocumentChunk.source_id == source_id)
    if line is not None and line > 0:
        query = query.filter(
            or_(DocumentChunk.start_line.is_(None), DocumentChunk.start_line <= line),
            or_(DocumentChunk.end_line.is_(None), DocumentChunk.end_line >= line),
        )
    return query.order_by(DocumentChunk.start_line.asc().nullslast()).limit(3).all()


def chunk_header(chunk: DocumentChunk) -> str:
    """Format an indexed chunk's location for an LLM context header."""
    page = (chunk.metadata_json or {}).get("page")
    location = (
        f"Seite {page}, Zeile {chunk.start_line}-{chunk.end_line}"
        if page
        else f"Zeile {chunk.start_line}-{chunk.end_line}"
    )
    return f"{chunk.file_path} ({location})"


def build_pinned_context(
    *,
    pinned_file: Optional[str],
    pinned_line: Optional[int],
    pinned_label: Optional[str],
    pinned_context: Optional[str],
    pinned_chunks: list[DocumentChunk],
    repository_id: Optional[int],
) -> str:
    """Build trusted framing plus untrusted text for a user-focused object.

    Indexed chunks are preferred.  When a first repository sync has not produced
    chunks yet, the checked-out file is read in a deliberately small window.
    """
    context = ""
    if pinned_file:
        if pinned_chunks:
            chunk_context = "\n\n".join(
                f"File: {chunk_header(chunk)}\n{chunk.content}" for chunk in pinned_chunks
            )
            context = (
                "The user explicitly focused the following code object/file and asks about this "
                "context first:\n"
                f'<untrusted_pinned_code path="{pinned_file}">\n'
                f"Focused object: {pinned_label or pinned_file}\n{chunk_context}\n"
                "</untrusted_pinned_code>\n\n"
            )
        elif repository_id:
            # Import here: agent imports runtime connector code and must not become a
            # dependency of service-module import during API startup.
            from agent import get_repo_path

            full_path = get_repo_path(repository_id, pinned_file)
            if full_path and os.path.exists(full_path):
                try:
                    with open(full_path, "r", errors="ignore") as source_file:
                        lines = source_file.readlines()
                    if pinned_line:
                        start, end = max(1, pinned_line - 15), min(len(lines), pinned_line + 15)
                        location_note = f"Line: {pinned_line}\nCode snippet (lines {start}-{end}):"
                    else:
                        start, end = 1, min(len(lines), 500)
                        location_note = (
                            "File content:"
                            if end == len(lines)
                            else f"File content (first {end} lines):"
                        )
                    snippet = "".join(
                        f"{number}: {lines[number - 1]}" for number in range(start, end + 1)
                    )
                    context = (
                        "The user explicitly focused the following code object/file and asks about this "
                        "context first:\n"
                        f'<untrusted_pinned_file path="{pinned_file}">\n'
                        f"Focused object: {pinned_label or pinned_file}\n"
                        f"File: {pinned_file}\n{location_note}\n{snippet}\n"
                        "</untrusted_pinned_file>\n\n"
                    )
                except OSError:
                    # Retrieval remains useful even if a worktree disappears between
                    # repository resolution and this best-effort fallback.
                    pass

    if pinned_context:
        context = (
            "The user has focused the following object to ask a question about it:\n"
            f"<untrusted_focused_object>\n{pinned_context}\n</untrusted_focused_object>\n\n"
        ) + context
    return context


def build_chat_prompt(
    *,
    context: str,
    pinned_context: str,
    message: str,
    pinned_file: Optional[str],
    multi_project_names: list[str],
) -> str:
    """Return the user prompt with scope, pin and citation contracts attached."""
    if not (context or pinned_context):
        return message
    out_of_scope_note = ""
    if "--- OUT-OF-SCOPE GLOBAL KNOWLEDGE SOURCES ---" in context:
        out_of_scope_note = (
            "Instruction: The user is focused on this project. Please prioritize answering based on "
            "'IN-SCOPE REPOSITORY FILES' and 'IN-SCOPE PROJECT KNOWLEDGE SOURCES'. Only if the "
            "answer is not found there, you may refer to 'OUT-OF-SCOPE GLOBAL KNOWLEDGE SOURCES' "
            "and clearly state that it is out-of-scope information.\n\n"
        )
    scope_note = ""
    if len(multi_project_names) > 1:
        scope_note = (
            "Instruction: No project is selected and context spans multiple projects "
            f"({', '.join(multi_project_names)}). Do not blend or guess between projects; ask "
            "the user to select a project when the question is not genuinely cross-project.\n\n"
        )
    pin_note = ""
    if pinned_file:
        pin_note = (
            "Instruction: Treat the pinned code as the primary subject. Use retrieved files only "
            "as supporting context; if the pinned context is insufficient, say so clearly.\n\n"
        )
    citation_note = (
        "Instruction: Cite a file that genuinely informed the answer inline in backticks as "
        "`path/to/file.ext:line`, with exactly one line number. Cite extensionless knowledge "
        "sources by their exact title without a line number. Do not cite uninvolved context.\n\n"
    )
    return (
        "Context:\n<untrusted_context>\n"
        f"{pinned_context}{context}\n</untrusted_context>\n\n"
        f"{out_of_scope_note}{scope_note}{pin_note}{citation_note}Question: {message}\nAnswer:"
    )


def persist_assistant_message(
    *,
    db: Session,
    session_id: int,
    answer: str,
    sources: list[dict],
    model: str,
    provider: str,
    agent_steps: list,
    previous_message: Optional[ChatMessage],
) -> ChatMessage:
    """Atomically replace a regenerated reply and store the completed assistant turn."""
    if previous_message:
        db.delete(previous_message)
    message = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=answer,
        sources_json=sources,
        metadata_json={"model": model, "provider": provider, "agent_steps": agent_steps},
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
