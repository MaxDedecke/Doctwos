"""Admin-only access to data-minimal MCP tool-call audit entries."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import core.config as cfg
from core.db_setup import get_db
from core.teams import require_admin
from models.database import MCPToolAuditLog, User

router = APIRouter(prefix="/audit", tags=["audit"])


def _iso(value):
    return value.isoformat() if value else None


def _serialize(entry: MCPToolAuditLog) -> dict:
    return {
        "id": entry.id,
        "created_at": _iso(entry.created_at),
        "user_name": entry.user.username if entry.user else None,
        "chat_session_id": entry.chat_session_id,
        "chat_message_id": entry.chat_message_id,
        "project_id": entry.project_id,
        "project_name": entry.project.name if entry.project else None,
        "knowledge_source_id": entry.knowledge_source_id,
        "server_name": entry.server_name,
        "tool_name": entry.tool_name,
        "arguments": entry.arguments_json,
        "status": entry.status,
        "error_message": entry.error_message,
        "duration_ms": entry.duration_ms,
        "result_payload_bytes": entry.result_payload_bytes,
        "result_truncated": entry.result_truncated,
        "index_revision": entry.index_revision,
        "trace_id": entry.trace_id,
    }


@router.get("/mcp-tool-calls")
def list_mcp_tool_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None, pattern="^(success|error)$"),
    tool: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Return one page of MCP calls, newest first; access is restricted to administrators.

    ``total`` counts all entries matching the filters, so clients can page through
    large audit trails without loading them at once.
    """
    query = db.query(MCPToolAuditLog)
    if status:
        query = query.filter(MCPToolAuditLog.status == status)
    if tool and tool.strip():
        escaped = tool.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(MCPToolAuditLog.tool_name.ilike(f"%{escaped}%", escape="\\"))
    total = query.count()
    entries = (
        query.order_by(MCPToolAuditLog.created_at.desc(), MCPToolAuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "retention_days": cfg.MCP_AUDIT_RETENTION_DAYS,
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": [_serialize(entry) for entry in entries],
    }
