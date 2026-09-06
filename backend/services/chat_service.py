"""Testable application services used by the SSE chat endpoint.

The API router deliberately owns HTTP concerns (authorization, session selection and
``StreamingResponse``).  This module owns the chat-specific transformations which do
not need FastAPI and can therefore be exercised without running the route.
"""

import os
from collections.abc import AsyncIterator
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.database import ChatMessage, DocumentChunk


async def stream_agent_events(
    *, provider: str, model_name: Optional[str], api_key: Optional[str], base_url: Optional[str],
    system_prompt: str, prompt: str, temperature: Optional[float], repository_id: Optional[int],
    db: Session, mcp_clients: list, ollama_base_url: str, history: list[dict[str, Any]],
    project_id: Optional[int], user_id: int, session_id: int, user_message_id: int,
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
                    snippet = "".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))
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
    *, context: str, pinned_context: str, message: str, pinned_file: Optional[str],
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
    *, db: Session, session_id: int, answer: str, sources: list[dict], model: str,
    provider: str, agent_steps: list, previous_message: Optional[ChatMessage],
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
