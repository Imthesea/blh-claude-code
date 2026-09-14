"""MCP 客户端:JSON-RPC over stdio 传输,连接真实 MCP server。"""

import json
import re
import subprocess
import time

from ..tools.registry import Tool

PROTOCOL_VERSION = "2024-11-05"


class MCPClient:
    def __init__(self, name, command, args=None, timeout=30):
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.timeout = timeout
        self.process = None
        self._next_id = 1

    def start(self):
        self.process = subprocess.Popen(
            [self.command, *self.args], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace")
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "blh", "version": "0.1.0"},
        })
        if "error" in result:
            raise RuntimeError(f"initialize failed: {result['error']}")
        self._notify("notifications/initialized")

    def list_tools(self):
        result = self._request("tools/list", {})
        if "error" in result:
            raise RuntimeError(f"tools/list failed: {result['error']}")
        return result.get("tools", [])

    def call_tool(self, tool_name, arguments):
        result = self._request("tools/call",
                               {"name": tool_name, "arguments": arguments})
        if "error" in result:
            return f"MCP error: {result['error']}"
        content = result.get("content", [])
        text = "\n".join(c.get("text", "") for c in content
                         if isinstance(c, dict) and c.get("type") == "text")
        return text or "(empty result)"

    def close(self):
        if self.process is None:
            return
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    # ---- 帧编解码 ----
    def _request(self, method, params):
        rid = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": rid, "method": method,
                    "params": params})
        return self._read_response(rid)

    def _notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def _send(self, msg):
        self.process.stdin.write(json.dumps(msg) + "\n")
        self.process.stdin.flush()

    def _read_response(self, rid):
        deadline = time.time() + self.timeout
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError(f"MCP server '{self.name}' closed stdout")
            data = json.loads(line)
            if data.get("id") == rid:
                return data.get("result", {"error": data.get("error")})
            if time.time() > deadline:
                raise TimeoutError(f"MCP request timed out after {self.timeout}s")


_DISALLOWED = re.compile(r"[^a-zA-Z0-9_-]")


def normalize_mcp_name(name: str) -> str:
    normalized = _DISALLOWED.sub("_", name)
    if not normalized:
        raise ValueError("MCP names cannot normalize to an empty string")
    return normalized


class MCPRegistry:
    def __init__(self, registry, workdir):
        self.registry = registry
        self.workdir = workdir
        self.clients: dict[str, MCPClient] = {}
        self._origins: dict[str, str] = {}

    def connect(self, name, command, args=None) -> str:
        if not name:
            return "Error: server name is required"
        if name in self.clients:
            return f"MCP server '{name}' already connected"
        safe_server = normalize_mcp_name(name)
        client = MCPClient(name, command, args)
        try:
            client.start()
            tools = client.list_tools()
        except Exception as exc:  # noqa: BLE001 - 连接失败转为错误消息返回给模型
            client.close()
            return f"Error: failed to connect MCP server '{name}': {exc}"
        registered = []
        for tool_def in tools:
            raw_name = tool_def.get("name", "")
            if not raw_name:
                continue
            safe_tool = normalize_mcp_name(raw_name)
            prefixed = f"mcp__{safe_server}__{safe_tool}"
            if len(prefixed) > 64:
                return f"Error: MCP tool name too long: {prefixed}"
            if prefixed in self._origins:
                return f"Error: MCP tool name collision: {prefixed}"
            schema = tool_def.get("inputSchema", {})
            self._origins[prefixed] = f"MCP tool '{name}/{raw_name}'"
            self.registry.register(Tool(
                name=prefixed,
                description=tool_def.get("description", ""),
                parameters=schema if isinstance(schema, dict) else
                {"type": "object", "properties": {}},
                handler=self._make_handler(client, raw_name),
            ))
            registered.append(prefixed)
        self.clients[name] = client
        names = ", ".join(registered) or "none"
        return (f"Connected to MCP server '{name}'. "
                f"Discovered {len(registered)} tools: {names}")

    def system_prompt_section(self) -> str:
        if not self.clients:
            return ""
        return "Connected MCP servers: " + ", ".join(self.clients)

    @staticmethod
    def _make_handler(client, raw_name):
        def handler(**kwargs):
            return client.call_tool(raw_name, kwargs)
        return handler
