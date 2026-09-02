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
        "trace_id": entry.trace_id,
    }


@router.get("/mcp-tool-calls")
def list_mcp_tool_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Return recent MCP calls; access is restricted to administrators."""
    entries = (
        db.query(MCPToolAuditLog)
        .order_by(MCPToolAuditLog.created_at.desc(), MCPToolAuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "retention_days": cfg.MCP_AUDIT_RETENTION_DAYS,
        "entries": [_serialize(entry) for entry in entries],
    }
