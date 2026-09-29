from services.mcp_audit import record_mcp_tool_call, sanitize_mcp_arguments
from models.database import MCPToolAuditLog


def test_sanitize_mcp_arguments_removes_secrets_and_bounds_values():
    sanitized = sanitize_mcp_arguments(
        {
            "jql": "project = DEMO",
            "api_token": "do-not-store",
            "nested": {"Authorization": "Bearer secret-value"},
            "url": "https://example.test/search?token=do-not-store&query=demo",
            "error_text": "request failed token=embedded-secret",
            "large": "x" * 600,
        }
    )

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
    assert set(response.json()) == {"retention_days", "total", "offset", "limit", "entries"}


def _seed_audit_entries(db_session, tool_name, count, *, failing_every=0):
    for index in range(count):
        record_mcp_tool_call(
            db_session,
            user_id=None,
            chat_session_id=None,
            chat_message_id=None,
            project_id=None,
            knowledge_source_id=None,
            server_name="paging-test",
            tool_name=tool_name,
            arguments={"n": index},
            success=not (failing_every and index % failing_every == 0),
            duration_ms=index,
        )


def _cleanup_audit_entries(db_session, tool_name):
    db_session.query(MCPToolAuditLog).filter(MCPToolAuditLog.tool_name == tool_name).delete()
    db_session.commit()


def test_mcp_audit_endpoint_pages_newest_first_with_total(client, db_session):
    tool = "paging_probe_tool"
    _seed_audit_entries(db_session, tool, 25)
    try:
        first = client.get("/audit/mcp-tool-calls", params={"tool": tool, "limit": 20, "offset": 0}).json()
        second = client.get("/audit/mcp-tool-calls", params={"tool": tool, "limit": 20, "offset": 20}).json()

        assert first["total"] == second["total"] == 25
        assert len(first["entries"]) == 20
        assert len(second["entries"]) == 5
        ids = [entry["id"] for entry in first["entries"] + second["entries"]]
        assert ids == sorted(ids, reverse=True)
        assert len(set(ids)) == 25
    finally:
        _cleanup_audit_entries(db_session, tool)


def test_mcp_audit_endpoint_filters_by_status_and_tool_substring(client, db_session):
    tool = "filter_probe_tool"
    _seed_audit_entries(db_session, tool, 6, failing_every=3)  # indexes 0 and 3 fail
    try:
        errors = client.get("/audit/mcp-tool-calls", params={"tool": "FILTER_PROBE", "status": "error"}).json()
        assert errors["total"] == 2
        assert {entry["status"] for entry in errors["entries"]} == {"error"}

        successes = client.get("/audit/mcp-tool-calls", params={"tool": tool, "status": "success"}).json()
        assert successes["total"] == 4

        # LIKE wildcards in user input must match literally, not as patterns.
        assert client.get("/audit/mcp-tool-calls", params={"tool": "filter%tool"}).json()["total"] == 0
    finally:
        _cleanup_audit_entries(db_session, tool)


def test_mcp_audit_endpoint_rejects_unknown_status(client):
    assert client.get("/audit/mcp-tool-calls", params={"status": "bogus"}).status_code == 422
