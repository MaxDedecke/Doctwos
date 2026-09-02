"""Persistence and redaction helpers for MCP tool-call auditing."""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import core.config as cfg
from core.tracing import get_trace_id
from models.database import MCPToolAuditLog

logger = logging.getLogger(__name__)

_MAX_STRING_LENGTH = 500
_MAX_ERROR_LENGTH = 1000
_MAX_COLLECTION_ITEMS = 50
_MAX_RECURSION_DEPTH = 6
_SENSITIVE_KEY_RE = re.compile(
    r"(?:token|secret|password|passwd|api[_-]?key|authorization|cookie|credential|private[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_SENSITIVE_PARAMETER_RE = re.compile(
    r"((?:[?&\s]|^)(?:token|secret|password|passwd|api[_-]?key|authorization|cookie|credential|access[_-]?token|refresh[_-]?token)\s*=\s*)[^\s&#,;]+",
    re.IGNORECASE,
)


def _redact_url(value: str) -> str:
    """Remove secret-looking query parameters while preserving useful URL context."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value
    query = [
        (key, "[REDACTED]" if _SENSITIVE_KEY_RE.search(key) else val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def _redact_string(value: str, max_length: int = _MAX_STRING_LENGTH) -> str:
    text = _BEARER_RE.sub("[REDACTED_AUTH]", value)
    text = _SENSITIVE_PARAMETER_RE.sub(r"\1[REDACTED]", text)
    if text.startswith(("http://", "https://")):
        text = _redact_url(text)
    if len(text) > max_length:
        return f"{text[:max_length]}…"
    return text


def sanitize_mcp_arguments(value: Any, _depth: int = 0) -> Any:
    """Return JSON-safe arguments with credentials removed and values bounded."""
    if _depth > _MAX_RECURSION_DEPTH:
        return "[MAX_DEPTH]"
    if isinstance(value, dict):
        sanitized = {}
        for raw_key, raw_value in list(value.items())[:_MAX_COLLECTION_ITEMS]:
            key = _redact_string(str(raw_key), 120)
            sanitized[key] = "[REDACTED]" if _SENSITIVE_KEY_RE.search(key) else sanitize_mcp_arguments(raw_value, _depth + 1)
        if len(value) > _MAX_COLLECTION_ITEMS:
            sanitized["_truncated"] = True
        return sanitized
    if isinstance(value, (list, tuple)):
        sanitized = [sanitize_mcp_arguments(item, _depth + 1) for item in value[:_MAX_COLLECTION_ITEMS]]
        if len(value) > _MAX_COLLECTION_ITEMS:
            sanitized.append("[TRUNCATED]")
        return sanitized
    if isinstance(value, str):
        return _redact_string(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_string(str(value))


def _sanitize_error(value: Any) -> str | None:
    if value is None:
        return None
    return _redact_string(str(value), _MAX_ERROR_LENGTH)


def record_mcp_tool_call(
    db,
    *,
    user_id: int | None,
    chat_session_id: int | None,
    chat_message_id: int | None,
    project_id: int | None,
    knowledge_source_id: int | None,
    server_name: str,
    tool_name: str,
    arguments: Any,
    success: bool,
    duration_ms: int,
    error_message: Any = None,
) -> None:
    """Persist one call without allowing audit failures to break the chat turn."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=cfg.MCP_AUDIT_RETENTION_DAYS)
        db.query(MCPToolAuditLog).filter(MCPToolAuditLog.created_at < cutoff).delete(synchronize_session=False)
        db.add(MCPToolAuditLog(
            user_id=user_id,
            chat_session_id=chat_session_id,
            chat_message_id=chat_message_id,
            project_id=project_id,
            knowledge_source_id=knowledge_source_id,
            server_name=_redact_string(server_name, 120),
            tool_name=_redact_string(tool_name, 200),
            arguments_json=sanitize_mcp_arguments(arguments),
            status="success" if success else "error",
            error_message=_sanitize_error(error_message),
            duration_ms=max(0, min(int(duration_ms), 2_147_483_647)),
            trace_id=_redact_string(get_trace_id(), 128),
        ))
        db.commit()
    except Exception:
        # Auditing is intentionally best-effort. A database issue must not turn a
        # successful external tool call into a failed user-visible chat request.
        db.rollback()
        logger.exception("Failed to persist MCP tool audit entry")
