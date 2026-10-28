import asyncio
import json
import logging
import os
from urllib.parse import urlparse

from typing import Dict, List, Any, Optional


logger = logging.getLogger(__name__)

# Domain suffixes mcp-atlassian itself treats as Atlassian Cloud
# (mcp_atlassian.utils.urls.is_atlassian_cloud_url) — reimplemented here
# instead of imported so a future mcp-atlassian internals refactor can't
# silently break knowledge-source setup; this list only needs to track the
# handful of Cloud domains Atlassian actually uses, not their SSRF/DNS checks.
_ATLASSIAN_CLOUD_SUFFIXES = (".atlassian.net", ".jira.com", ".jira-dev.com", ".atlassian.com")


def _is_atlassian_cloud_url(url: str) -> bool:
    """Cloud vs. Server/Data Center — on-prem installs use the customer's own
    domain, Cloud always lives under one of the suffixes above."""
    host = (urlparse(url).hostname or "").lower()
    return host == "api.atlassian.com" or host.endswith(_ATLASSIAN_CLOUD_SUFFIXES)


def _atlassian_auth_env(prefix: str, src) -> Dict[str, str]:
    """Auth env vars for one mcp-atlassian product ("JIRA" or "CONFLUENCE").

    Mirrors mcp-atlassian's own precedence (mcp_atlassian.*.config.py's
    from_env()): Server/Data Center accepts a bare Personal Access Token
    (CONFLUENCE_PERSONAL_TOKEN/JIRA_PERSONAL_TOKEN, no username) or
    username+API token; Cloud only supports username (email) + API token —
    there's no Cloud PAT. "No username set -> treat the token as a PAT" is
    the same convention connectors.py's _bitbucket_server_auth already uses
    for Bitbucket Server, so this app's data model (nullable `username`)
    needs no change to support it here too.
    """
    if not _is_atlassian_cloud_url(src.url) and not src.username:
        return {f"{prefix}_PERSONAL_TOKEN": src.token}
    return {
        f"{prefix}_USERNAME": src.username or "",
        f"{prefix}_API_TOKEN": src.token,
    }


class MCPClient:
    """
    A lightweight, native JSON-RPC 2.0 client for Model Context Protocol (MCP) servers.
    Communicates with MCP server subprocesses over stdin/stdout.
    """

    def __init__(
        self,
        name: str,
        command: str,
        args: List[str],
        env: Dict[str, str],
        source_id: Optional[int] = None,
    ):
        self.name = name
        self.source_id = source_id
        self.command = command
        self.args = args
        self.env = env
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.next_id = 1
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._stderr_tail: List[str] = []

    async def start(self) -> bool:
        """Starts the MCP server subprocess and initiates the stdout read loop."""
        try:
            full_env = os.environ.copy()
            full_env.update(self.env)

            # Spawn the server process. limit raised from asyncio's 64 KiB default —
            # tools/list responses (mcp-atlassian exposes dozens of tools with full JSON schemas) can
            # exceed that and crash the stdout reader with a LimitOverrunError.
            # stderr is piped (not DEVNULL) and drained by _stderr_loop so a failed
            # spawn's actual error output is visible in logs instead of silently lost.
            self.proc = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
                limit=10 * 1024 * 1024,
            )
            # Start background reader tasks
            self._read_task = asyncio.create_task(self._read_loop())
            self._stderr_task = asyncio.create_task(self._stderr_loop())

            # Send standard MCP initialize request
            try:
                await self.send_request(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "doctus-mcp-client", "version": "1.0.0"},
                    },
                )
                # "initialized" ist eine JSON-RPC Notification (kein "id"-Feld, keine Antwort) —
                # über send_request verschickt bekam sie ein "id" und Server antworteten mit
                # "Method not found", da sie es als unbekannten Request behandelten.
                await self.send_notification("notifications/initialized", {})
                return True
            except Exception as e:
                logger.error(
                    "Error initializing MCP server %s: %s%s",
                    self.name,
                    e,
                    (" | stderr: " + " | ".join(self._stderr_tail)) if self._stderr_tail else "",
                )
                await self.stop()
                return False
        except Exception as e:
            logger.error("Failed to start MCP server %s process: %s", self.name, e)
            return False

    async def _stderr_loop(self):
        """Drains the subprocess's stderr so it never blocks on a full pipe, and keeps
        the last few lines around so start() can surface them if init fails."""
        try:
            while self.proc and self.proc.stderr:
                line = await self.proc.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip()
                if text:
                    logger.debug("[%s stderr] %s", self.name, text)
                    self._stderr_tail.append(text)
                    self._stderr_tail = self._stderr_tail[-20:]
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Exception in stderr reader loop for %s: %s", self.name, e)

    async def _read_loop(self):
        """Asynchronously reads JSON-RPC messages from stdout and resolves pending futures."""
        try:
            while self.proc and self.proc.stdout:
                line = await self.proc.stdout.readline()
                if not line:
                    break

                try:
                    data = json.loads(line.decode().strip())
                    if "id" in data:
                        req_id = data["id"]
                        if req_id in self._pending_requests:
                            future = self._pending_requests[req_id]
                            if not future.done():
                                future.set_result(data)
                except Exception as e:
                    logger.error("Error parsing JSON-RPC line from %s: %s", self.name, e)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Exception in stdout reader loop for %s: %s", self.name, e)

    async def send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sends a request to the MCP server and awaits its response."""
        if not self.proc or not self.proc.stdin:
            raise Exception(f"MCP server {self.name} is not running")

        req_id = self.next_id
        self.next_id += 1

        future = asyncio.get_event_loop().create_future()
        self._pending_requests[req_id] = future

        request = {"jsonrpc": "2.0", "method": method, "id": req_id, "params": params}

        payload = json.dumps(request) + "\n"
        self.proc.stdin.write(payload.encode())
        await self.proc.stdin.drain()

        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            if "error" in response:
                raise Exception(response["error"].get("message", "Unknown error"))
            return response.get("result", {})
        finally:
            self._pending_requests.pop(req_id, None)

    async def send_notification(self, method: str, params: Dict[str, Any]) -> None:
        """Sends a JSON-RPC notification (no 'id', no response expected) to the MCP server."""
        if not self.proc or not self.proc.stdin:
            raise Exception(f"MCP server {self.name} is not running")

        notification = {"jsonrpc": "2.0", "method": method, "params": params}
        payload = json.dumps(notification) + "\n"
        self.proc.stdin.write(payload.encode())
        await self.proc.stdin.drain()

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Lists all tools exposed by the MCP server."""
        try:
            res = await self.send_request("tools/list", {})
            return res.get("tools", [])
        except Exception as e:
            logger.error("Failed to list tools from %s: %s", self.name, e)
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Calls a specific tool on the MCP server."""
        return await self.send_request("tools/call", {"name": tool_name, "arguments": arguments})

    async def stop(self):
        """Stops the reader tasks and terminates the subprocess."""
        if self._read_task:
            self._read_task.cancel()
            self._read_task = None
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None
        if self.proc:
            try:
                self.proc.terminate()
                await self.proc.wait()
            except Exception:
                pass
            self.proc = None


# Helper to build and run MCP Clients for active knowledge sources
async def init_mcp_clients_for_sources(sources: List[Any], status_callback=None) -> List[MCPClient]:
    clients = []
    for src in sources:
        src_type = src.type.lower() if src.type else ""
        server_name = f"{src_type}-{src.id}"
        if not src.token:
            if status_callback:
                status_callback(
                    {"server": server_name, "available": False, "status": "not_configured"}
                )
            continue
        if not src.url:
            if status_callback:
                status_callback(
                    {"server": server_name, "available": False, "status": "not_configured"}
                )
            continue

        if src_type == "jira":
            # mcp-atlassian (sooperset/mcp-atlassian, PyPI) — a single process
            # only gets JIRA_* env set here, so it exposes just the Jira toolset
            # (see mcp_atlassian.servers.main: each product's tools are gated on
            # its own config being present). Cloud and Server/Data Center both
            # supported — see _atlassian_auth_env() above.
            env = {
                "JIRA_URL": src.url,
                **_atlassian_auth_env("JIRA", src),
            }
            client = MCPClient(
                name=f"jira-{src.id}",
                command="mcp-atlassian",
                args=[],
                env=env,
                source_id=src.id,
            )
            started = await client.start()
            if status_callback:
                status_callback(
                    {
                        "server": server_name,
                        "available": bool(started),
                        "status": "connected" if started else "unavailable",
                    }
                )
            if started:
                clients.append(client)

        elif src_type == "confluence":
            # Confluence Cloud's REST API lives under a "/wiki" path prefix
            # (mcp-atlassian's own error message uses
            # "https://your-company.atlassian.net/wiki" as the example) — Server/
            # Data Center installs don't have this prefix by default, so it must
            # only be appended for Cloud URLs. db_source.url stores the bare site
            # root (see connectors.py's /connectors/test, which appends
            # "/wiki/rest/api/space" itself for its own Cloud probe).
            base_url = src.url.rstrip("/")
            if _is_atlassian_cloud_url(base_url):
                confluence_url = base_url if base_url.endswith("/wiki") else f"{base_url}/wiki"
            else:
                confluence_url = base_url
            env = {
                "CONFLUENCE_URL": confluence_url,
                **_atlassian_auth_env("CONFLUENCE", src),
            }
            client = MCPClient(
                name=f"confluence-{src.id}",
                command="mcp-atlassian",
                args=[],
                env=env,
                source_id=src.id,
            )
            started = await client.start()
            if status_callback:
                status_callback(
                    {
                        "server": server_name,
                        "available": bool(started),
                        "status": "connected" if started else "unavailable",
                    }
                )
            if started:
                clients.append(client)

    return clients
