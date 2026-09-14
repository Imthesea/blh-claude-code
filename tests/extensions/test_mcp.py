import sys

import pytest

from blh.extensions.mcp import MCPClient, MCPRegistry, normalize_mcp_name
from blh.tools.registry import ToolRegistry

SERVER_CODE = r'''
import json, sys

def reply(req, result):
    json.dump({"jsonrpc": "2.0", "id": req["id"], "result": result}, sys.stdout)
    sys.stdout.write("\n"); sys.stdout.flush()

TOOLS = [
    {"name": "search", "description": "Search docs.",
     "inputSchema": {"type": "object",
                     "properties": {"query": {"type": "string"}},
                     "required": ["query"]}},
]
for line in sys.stdin:
    req = json.loads(line)
    method = req.get("method")
    if method == "initialize":
        reply(req, {"protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake", "version": "1.0"}})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        reply(req, {"tools": TOOLS})
    elif method == "tools/call":
        params = req["params"]
        if params["name"] != "search":
            reply(req, {"content": [{"type": "text",
                                     "text": f"unknown tool: {params['name']}"}],
                        "isError": True})
        else:
            args = params["arguments"]
            reply(req, {"content": [{"type": "text",
                                     "text": f"searched {args.get('query')}"}],
                        "isError": False})
    else:
        reply(req, {"content": [], "isError": False})
'''


def _start_client():
    return MCPClient("fake", sys.executable, ["-c", SERVER_CODE])


def test_initialize_and_list_tools():
    client = _start_client()
    try:
        client.start()
        tools = client.list_tools()
        assert [t["name"] for t in tools] == ["search"]
    finally:
        client.close()


def test_call_tool():
    client = _start_client()
    try:
        client.start()
        assert client.call_tool("search", {"query": "x"}) == "searched x"
    finally:
        client.close()


def test_call_unknown_tool():
    client = _start_client()
    try:
        client.start()
        assert "unknown tool" in client.call_tool("nope", {})
    finally:
        client.close()


def test_normalize_mcp_name():
    assert normalize_mcp_name("docs.one/get") == "docs_one_get"


def test_normalize_mcp_name_empty_raises():
    with pytest.raises(ValueError):
        normalize_mcp_name("")


def test_connect_registers_prefixed_tools():
    registry = ToolRegistry()
    mcp = MCPRegistry(registry, ".")
    result = mcp.connect("fake", sys.executable, ["-c", SERVER_CODE])
    assert "fake" in result
    names = [s["function"]["name"] for s in registry.schemas()]
    assert "mcp__fake__search" in names


def test_connect_duplicate_returns_message():
    registry = ToolRegistry()
    mcp = MCPRegistry(registry, ".")
    mcp.connect("fake", sys.executable, ["-c", SERVER_CODE])
    assert "already connected" in mcp.connect("fake", sys.executable,
                                              ["-c", SERVER_CODE])


def test_system_prompt_section():
    registry = ToolRegistry()
    mcp = MCPRegistry(registry, ".")
    assert mcp.system_prompt_section() == ""
    mcp.connect("fake", sys.executable, ["-c", SERVER_CODE])
    assert "fake" in mcp.system_prompt_section()

