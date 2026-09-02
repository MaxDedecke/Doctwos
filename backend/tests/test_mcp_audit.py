from services.mcp_audit import record_mcp_tool_call, sanitize_mcp_arguments
from models.database import MCPToolAuditLog


def test_sanitize_mcp_arguments_removes_secrets_and_bounds_values():
    sanitized = sanitize_mcp_arguments({
        "jql": "project = DEMO",
        "api_token": "do-not-store",
        "nested": {"Authorization": "Bearer secret-value"},
        "url": "https://example.test/search?token=do-not-store&query=demo",
        "error_text": "request failed token=embedded-secret",
        "large": "x" * 600,
    })

    assert sanitized["jql"] == "project = DEMO"
    assert sanitized["api_token"] == "[REDACTED]"
    assert sanitized["nested"]["Authorization"] == "[REDACTED]"
    assert sanitized["url"] == "https://example.test/search?token=%5BREDACTED%5D&query=demo"
    assert sanitized["error_text"] == "request failed token=[REDACTED]"
    assert len(sanitized["large"]) == 501


def test_record_mcp_tool_call_persists_only_redacted_arguments(db_session):
    record_mcp_tool_call(
        db_session,
        user_id=None,
        chat_session_id=None,
        chat_message_id=None,
        project_id=None,
        knowledge_source_id=None,
        server_name="jira-12",
        tool_name="search_issues",
        arguments={"jql": "project = DEMO", "token": "secret"},
        success=True,
        duration_ms=42,
    )

    entry = db_session.query(MCPToolAuditLog).order_by(MCPToolAuditLog.id.desc()).first()
    assert entry is not None
    assert entry.tool_name == "search_issues"
    assert entry.arguments_json == {"jql": "project = DEMO", "token": "[REDACTED]"}
    assert entry.status == "success"
    assert entry.duration_ms == 42

    db_session.delete(entry)
    db_session.commit()


def test_mcp_audit_endpoint_requires_authentication(unauthenticated_client):
    response = unauthenticated_client.get("/audit/mcp-tool-calls")
    assert response.status_code == 401


def test_mcp_audit_endpoint_is_admin_only(member_client):
    response = member_client.get("/audit/mcp-tool-calls")
    assert response.status_code == 403


def test_admin_can_read_mcp_audit_endpoint(client):
    response = client.get("/audit/mcp-tool-calls")
    assert response.status_code == 200
    assert set(response.json()) == {"retention_days", "entries"}
