"""MCP-Werkzeuge der angebundenen Server für den Chat-Agenten sammeln, samt Preflight-Ereignis für die Oberfläche."""

import logging
from typing import Any

from mcp_client import MCPClient

logger = logging.getLogger(__name__)


async def collect_mcp_tools(
    mcp_clients: list[MCPClient], mcp_initialization_status: list[dict[str, Any]] | None
) -> tuple[list[dict], dict[str, MCPClient], dict[str, Any]]:
    mcp_tools_def = []
    mcp_tool_map = {}
    mcp_preflight_servers = []
    for client in mcp_clients:
        try:
            tools = await client.list_tools()
            mcp_preflight_servers.append(
                {
                    "server": client.name,
                    "available": True,
                    "tool_count": len(tools),
                    "tools": [tool.get("name") for tool in tools if tool.get("name")],
                }
            )
            for t in tools:
                name = t["name"]
                mcp_tool_map[name] = client
                mcp_tools_def.append(t)
        except Exception as e:
            logger.error(f"Error listing tools for MCP client {client.name}: {e}")
            mcp_preflight_servers.append(
                {
                    "server": client.name,
                    "available": False,
                    "tool_count": 0,
                    "tools": [],
                    "error": str(e)[:240],
                }
            )

    preflight_by_server = {item["server"]: item for item in mcp_preflight_servers}
    for item in mcp_initialization_status or []:
        current = preflight_by_server.get(item.get("server"))
        if current is None or not item.get("available"):
            preflight_by_server[item.get("server", "unknown")] = {
                **item,
                "tool_count": current.get("tool_count", 0) if current else 0,
                "tools": current.get("tools", []) if current else [],
            }
    mcp_preflight_servers = list(preflight_by_server.values())
    mcp_preflight = {
        "type": "mcp_preflight",
        "status": "ready"
        if any(item.get("available") for item in mcp_preflight_servers)
        else ("unavailable" if mcp_preflight_servers else "not_configured"),
        "servers": mcp_preflight_servers,
        "tool_count": sum(item.get("tool_count", 0) for item in mcp_preflight_servers),
    }
    return mcp_tools_def, mcp_tool_map, mcp_preflight
