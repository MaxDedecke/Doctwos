"""Source visibility and numbered source excerpts shared by the MCP server and the evidence blocks."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.projects import assert_knowledge_source_visible
from models.database import CodeEntity, DocumentChunk, KnowledgeSource, User

COMMENT_START = ("//", "/*", "*", "#", "--")


def numbered(text: str, start_line: int, compact: bool = False) -> str:
    """Line-numbered text; compact drops blank, comment-only and COBOL comment lines but keeps the original numbers."""
    out = []
    for i, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if compact and (not stripped or stripped.startswith(COMMENT_START) or (len(line) > 6 and line[6] == "*")):
            continue
        out.append(f"{start_line + i}: {line}")
    return "\n".join(out)


def source_visible(db: Session, user: User, source_id: int | None) -> bool:
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


def site_excerpt(db: Session, user: User, entity: CodeEntity, line: int, radius: int = 10) -> dict | None:
    """Numbered source lines around one call site, read from the indexed chunks of that file."""
    if not source_visible(db, user, entity.source_id):
        return None
    low, high = max(1, line - radius), line + radius
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.project_id == entity.project_id, DocumentChunk.source_id == entity.source_id,
        DocumentChunk.file_path == entity.file_path, DocumentChunk.start_line <= high, DocumentChunk.end_line >= low,
    ).order_by(DocumentChunk.start_line).limit(4).all()
    parts = []
    for chunk in chunks:
        first, last = max(low, chunk.start_line), min(high, chunk.end_line)
        if first <= last:
            lines = chunk.content.splitlines()
            parts.append(numbered("\n".join(lines[first - chunk.start_line:last - chunk.start_line + 1]), first))
    text = "\n".join(parts)[:2200]
    return {"file": entity.file_path, "around_line": line, "text": text} if text else None
