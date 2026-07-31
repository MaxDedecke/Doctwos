import asyncio
import json
import logging
import os
import sys
import httpx
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class MCPClient:
    """
    A lightweight, native JSON-RPC 2.0 client for Model Context Protocol (MCP) servers.
    Communicates with MCP server subprocesses over stdin/stdout.
    """
    def __init__(self, name: str, command: str, args: List[str], env: Dict[str, str]):
        self.name = name
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
                limit=10 * 1024 * 1024
            )
            # Start background reader tasks
            self._read_task = asyncio.create_task(self._read_loop())
            self._stderr_task = asyncio.create_task(self._stderr_loop())

            # Send standard MCP initialize request
            try:
                await self.send_request("initialize", {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "doctus-mcp-client", "version": "1.0.0"}
                })
                # "initialized" ist eine JSON-RPC Notification (kein "id"-Feld, keine Antwort) —
                # über send_request verschickt bekam sie ein "id" und Server antworteten mit
                # "Method not found", da sie es als unbekannten Request behandelten.
                await self.send_notification("notifications/initialized", {})
                return True
            except Exception as e:
                logger.error(
                    "Error initializing MCP server %s: %s%s", self.name, e,
                    (" | stderr: " + " | ".join(self._stderr_tail)) if self._stderr_tail else ""
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
        
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "id": req_id,
            "params": params
        }
        
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

        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
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
        return await self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

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
async def init_mcp_clients_for_sources(sources: List[Any]) -> List[MCPClient]:
    clients = []
    for src in sources:
        if not src.token:
            continue

        src_type = src.type.lower() if src.type else ""
        if not src.url:
            continue

        if src_type == "jira":
            # mcp-atlassian (sooperset/mcp-atlassian, PyPI) — a single process
            # only gets JIRA_* env set here, so it exposes just the Jira toolset
            # (see mcp_atlassian.servers.main: each product's tools are gated on
            # its own config being present). Cloud auth only, matching this app's
            # data model (username=email + API token; there's no separate PAT field
            # for Server/Data Center instances — see connectors.py's /connectors/test).
            env = {
                "JIRA_URL": src.url,
                "JIRA_USERNAME": src.username or "",
                "JIRA_API_TOKEN": src.token,
            }
            client = MCPClient(
                name=f"jira-{src.id}",
                command="mcp-atlassian",
                args=[],
                env=env
            )
            if await client.start():
                clients.append(client)

        elif src_type == "confluence":
            # mcp-atlassian requires the full wiki URL (docs/error message both say
            # ".../wiki"), but db_source.url stores the bare site root (see
            # connectors.py's /connectors/test, which appends "/wiki/rest/api/space"
            # itself) — append it here too, unless already present.
            base_url = src.url.rstrip("/")
            confluence_url = base_url if base_url.endswith("/wiki") else f"{base_url}/wiki"
            env = {
                "CONFLUENCE_URL": confluence_url,
                "CONFLUENCE_USERNAME": src.username or "",
                "CONFLUENCE_API_TOKEN": src.token,
            }
            client = MCPClient(
                name=f"confluence-{src.id}",
                command="mcp-atlassian",
                args=[],
                env=env
            )
            if await client.start():
                clients.append(client)

    return clients


# Coordinates the tool-calling loop for LLMs supporting function calling
async def execute_chat_with_mcp(
    provider: str,
    model_name: str,
    api_key: str,
    base_url: str,
    system_prompt: str,
    prompt: str,
    temperature: float,
    mcp_clients: List[MCPClient]
) -> Optional[str]:
    """
    Lists tools from all active MCP clients, registers them in the LLM call,
    and executes tool-calls returned by the model in a loop (up to 5 turns).
    """
    mcp_tools = []
    tool_map = {}
    
    # Gather tools
    for client in mcp_clients:
        tools = await client.list_tools()
        for t in tools:
            name = t["name"]
            tool_map[name] = client
            mcp_tools.append(t)
            
    if not mcp_tools:
        return None # No tools available; fallback to standard prompt injection
        
    print(f"MCP: Registered {len(mcp_tools)} tools for execution", file=sys.stderr)
    sys.stderr.flush()

    if provider == "openai":
        url = base_url or "https://api.openai.com/v1"
        if url.endswith("/"):
            url = url[:-1]
        full_url = url if "/chat/completions" in url else f"{url}/chat/completions"
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        openai_tools = []
        for t in mcp_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("inputSchema", {"type": "object", "properties": {}})
                }
            })
            
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        async with httpx.AsyncClient(timeout=120.0) as client_http:
            for turn in range(5):
                payload = {
                    "model": model_name or "gpt-4o",
                    "messages": messages,
                    "temperature": temperature if temperature is not None else 0.7,
                    "tools": openai_tools
                }
                
                resp = await client_http.post(full_url, json=payload, headers=headers)
                resp.raise_for_status()
                res_data = resp.json()
                
                choice = res_data["choices"][0]
                msg = choice["message"]
                messages.append(msg)
                
                if choice.get("finish_reason") == "tool_calls" or msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]
                    for tc in tool_calls:
                        tc_id = tc["id"]
                        fn = tc["function"]
                        fn_name = fn["name"]
                        fn_args = json.loads(fn["arguments"])
                        
                        mcp_client = tool_map.get(fn_name)
                        if mcp_client:
                            print(f"MCP: Calling tool {fn_name} on {mcp_client.name}", file=sys.stderr)
                            sys.stderr.flush()
                            try:
                                tool_res = await mcp_client.call_tool(fn_name, fn_args)
                                text_content = ""
                                for item in tool_res.get("content", []):
                                    if item.get("type") == "text":
                                        text_content += item.get("text", "")
                                if not text_content:
                                    text_content = json.dumps(tool_res)
                            except Exception as ex:
                                text_content = f"Error calling tool: {ex}"
                        else:
                            text_content = f"Error: Tool {fn_name} not found"
                            
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": fn_name,
                            "content": text_content
                        })
                else:
                    return msg.get("content", "")
            return "MCP: Maximum tool calling iterations exceeded."

    elif provider == "anthropic":
        full_url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key or "",
            "anthropic-version": "2023-06-01"
        }
        
        anthropic_tools = []
        for t in mcp_tools:
            anthropic_tools.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("inputSchema", {"type": "object", "properties": {}})
            })
            
        messages = [{"role": "user", "content": prompt}]
        
        async with httpx.AsyncClient(timeout=120.0) as client_http:
            for turn in range(5):
                payload = {
                    "model": model_name or "claude-3-5-sonnet-20241022",
                    "max_tokens": 4096,
                    "messages": messages,
                    "temperature": temperature if temperature is not None else 0.7,
                    "tools": anthropic_tools
                }
                if system_prompt:
                    payload["system"] = system_prompt
                    
                resp = await client_http.post(full_url, json=payload, headers=headers)
                resp.raise_for_status()
                res_data = resp.json()
                
                assistant_blocks = res_data["content"]
                messages.append({"role": "assistant", "content": assistant_blocks})
                
                tool_calls = [b for b in assistant_blocks if b.get("type") == "tool_use"]
                if tool_calls:
                    tool_result_content = []
                    for tc in tool_calls:
                        tc_id = tc["id"]
                        fn_name = tc["name"]
                        fn_args = tc["input"]
                        
                        mcp_client = tool_map.get(fn_name)
                        if mcp_client:
                            print(f"MCP: Calling tool {fn_name} on {mcp_client.name}", file=sys.stderr)
                            sys.stderr.flush()
                            try:
                                tool_res = await mcp_client.call_tool(fn_name, fn_args)
                                text_content = ""
                                for item in tool_res.get("content", []):
                                    if item.get("type") == "text":
                                        text_content += item.get("text", "")
                                if not text_content:
                                    text_content = json.dumps(tool_res)
                            except Exception as ex:
                                text_content = f"Error calling tool: {ex}"
                        else:
                            text_content = f"Error: Tool {fn_name} not found"
                            
                        tool_result_content.append({
                            "type": "tool_result",
                            "tool_use_id": tc_id,
                            "content": text_content
                        })
                    messages.append({"role": "user", "content": tool_result_content})
                else:
                    text_blocks = [b for b in assistant_blocks if b.get("type") == "text"]
                    return "".join([b.get("text", "") for b in text_blocks])
            return "MCP: Maximum tool calling iterations exceeded."

    elif provider == "gemini":
        gemini_tools = []
        declarations = []
        for t in mcp_tools:
            declarations.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("inputSchema", {"type": "object", "properties": {}})
            })
        gemini_tools.append({"functionDeclarations": declarations})
        
        full_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name or 'gemini-1.5-flash'}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        
        async with httpx.AsyncClient(timeout=120.0) as client_http:
            for turn in range(5):
                payload = {
                    "contents": contents,
                    "tools": gemini_tools,
                    "generationConfig": {
                        "temperature": temperature if temperature is not None else 0.7
                    }
                }
                if system_prompt:
                    payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
                    
                resp = await client_http.post(full_url, json=payload, headers=headers)
                resp.raise_for_status()
                res_data = resp.json()
                
                candidate = res_data["candidates"][0]
                assistant_content = candidate["content"]
                contents.append(assistant_content)
                
                parts = assistant_content.get("parts", [])
                function_calls = [p for p in parts if "functionCall" in p]
                
                if function_calls:
                    response_parts = []
                    for fc_part in function_calls:
                        fc = fc_part["functionCall"]
                        fn_name = fc["name"]
                        fn_args = fc.get("args", {})
                        
                        mcp_client = tool_map.get(fn_name)
                        if mcp_client:
                            print(f"MCP: Calling tool {fn_name} on {mcp_client.name}", file=sys.stderr)
                            sys.stderr.flush()
                            try:
                                tool_res = await mcp_client.call_tool(fn_name, fn_args)
                                text_content = ""
                                for item in tool_res.get("content", []):
                                    if item.get("type") == "text":
                                        text_content += item.get("text", "")
                                if not text_content:
                                    text_content = json.dumps(tool_res)
                            except Exception as ex:
                                text_content = f"Error calling tool: {ex}"
                        else:
                            text_content = f"Error: Tool {fn_name} not found"
                            
                        response_parts.append({
                            "functionResponse": {
                                "name": fn_name,
                                "response": {"result": text_content}
                            }
                        })
                    contents.append({"role": "user", "parts": response_parts})
                else:
                    return "".join([p.get("text", "") for p in parts if "text" in p])
            return "MCP: Maximum tool calling iterations exceeded."

    return None
