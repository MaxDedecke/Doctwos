"""
Tests for mcp_client.py's subprocess spawn (real MCP handshake against a fake
stdio server) and for init_mcp_clients_for_sources' per-source-type env/command
construction (jira/confluence via mcp-atlassian) — see
docs/TECH_DEBT_CLEANUP_PLAN.md §2 for why the previous npm package names were
wrong and non-functional.

Der Notion-Fall ist mit AP-0 entfallen: mit ihm verschwand der einzige Grund für
eine Node.js-Runtime im Backend-Image (F-049).
"""
import sys
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from mcp_client import MCPClient, init_mcp_clients_for_sources

# A minimal stdio JSON-RPC server standing in for a real MCP server: answers
# "initialize" and "tools/list", ignores the "initialized" notification.
_FAKE_SERVER_SCRIPT = textwrap.dedent("""
    import json, sys
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        if "id" not in req:
            continue  # notification, no response
        if req["method"] == "initialize":
            result = {"protocolVersion": "2024-11-05", "capabilities": {}}
        elif req["method"] == "tools/list":
            result = {"tools": [{"name": "fake_tool", "description": "d", "inputSchema": {}}]}
        else:
            result = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}) + "\\n")
        sys.stdout.flush()
""")


@pytest.fixture
def fake_server_script(tmp_path):
    path = tmp_path / "fake_mcp_server.py"
    path.write_text(_FAKE_SERVER_SCRIPT)
    return str(path)


@pytest.mark.asyncio
async def test_start_succeeds_against_a_real_stdio_handshake(fake_server_script):
    client = MCPClient(name="fake", command=sys.executable, args=[fake_server_script], env={})
    try:
        assert await client.start() is True
        tools = await client.list_tools()
        assert tools == [{"name": "fake_tool", "description": "d", "inputSchema": {}}]
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_start_returns_false_for_a_nonexistent_command():
    client = MCPClient(name="broken", command="this-binary-does-not-exist-xyz", args=[], env={})
    assert await client.start() is False
    assert client.proc is None


@pytest.mark.asyncio
async def test_jira_source_spawns_mcp_atlassian_with_cloud_env():
    src = SimpleNamespace(id=1, type="jira", url="https://example.atlassian.net", username="user@example.com", token="tok")
    with patch("mcp_client.MCPClient") as MockClient:
        MockClient.return_value.start = AsyncMock(return_value=True)
        clients = await init_mcp_clients_for_sources([src])
        assert len(clients) == 1
        _, kwargs = MockClient.call_args
        assert kwargs["command"] == "mcp-atlassian"
        assert kwargs["env"] == {
            "JIRA_URL": "https://example.atlassian.net",
            "JIRA_USERNAME": "user@example.com",
            "JIRA_API_TOKEN": "tok",
        }


@pytest.mark.asyncio
async def test_confluence_source_appends_wiki_suffix():
    src = SimpleNamespace(id=2, type="confluence", url="https://example.atlassian.net", username="user@example.com", token="tok")
    with patch("mcp_client.MCPClient") as MockClient:
        MockClient.return_value.start = AsyncMock(return_value=True)
        await init_mcp_clients_for_sources([src])
        _, kwargs = MockClient.call_args
        assert kwargs["command"] == "mcp-atlassian"
        assert kwargs["env"]["CONFLUENCE_URL"] == "https://example.atlassian.net/wiki"


@pytest.mark.asyncio
async def test_confluence_source_does_not_double_append_wiki_suffix():
    src = SimpleNamespace(id=3, type="confluence", url="https://example.atlassian.net/wiki", username="user@example.com", token="tok")
    with patch("mcp_client.MCPClient") as MockClient:
        MockClient.return_value.start = AsyncMock(return_value=True)
        await init_mcp_clients_for_sources([src])
        _, kwargs = MockClient.call_args
        assert kwargs["env"]["CONFLUENCE_URL"] == "https://example.atlassian.net/wiki"


@pytest.mark.asyncio
async def test_sources_without_a_token_are_skipped():
    src = SimpleNamespace(id=5, type="jira", url="https://example.atlassian.net", username="user@example.com", token=None)
    with patch("mcp_client.MCPClient") as MockClient:
        clients = await init_mcp_clients_for_sources([src])
        assert clients == []
        MockClient.assert_not_called()
