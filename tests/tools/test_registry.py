import json

from blh.tools.registry import Tool, ToolRegistry


def make_tool(name="echo"):
    return Tool(
        name=name,
        description="echo input",
        parameters={"type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"]},
        handler=lambda text: text,
    )


def test_register_and_schemas():
    reg = ToolRegistry()
    reg.register(make_tool())
    schemas = reg.schemas()
    assert schemas == [{
        "type": "function",
        "function": {
            "name": "echo",
            "description": "echo input",
            "parameters": {"type": "object",
                           "properties": {"text": {"type": "string"}},
                           "required": ["text"]},
        },
    }]


def test_dispatch_calls_handler():
    reg = ToolRegistry()
    reg.register(make_tool())
    assert reg.dispatch("echo", json.dumps({"text": "hi"})) == "hi"


def test_dispatch_unknown_tool():
    assert "unknown tool" in ToolRegistry().dispatch("nope", "{}")


def test_dispatch_invalid_json():
    reg = ToolRegistry()
    reg.register(make_tool())
    assert "invalid tool arguments" in reg.dispatch("echo", "{bad json")


def test_dispatch_handler_exception_returns_error():
    reg = ToolRegistry()
    reg.register(Tool("boom", "", {}, handler=lambda: 1 / 0))
    assert "failed" in reg.dispatch("boom", "{}")
