"""extensions 工具注册:load_skill + connect_mcp。"""

from ..tools.registry import Tool, ToolRegistry


def register_extension_tools(registry: ToolRegistry, skills, mcp) -> None:
    registry.register(Tool(
        name="load_skill",
        description="Load the full SKILL.md content by skill name.",
        parameters={"type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"]},
        handler=skills.load,
    ))
    registry.register(Tool(
        name="connect_mcp",
        description="Connect to an MCP server and discover its tools.",
        parameters={"type": "object",
                    "properties": {"name": {"type": "string"},
                                   "command": {"type": "string"},
                                   "args": {"type": "array",
                                           "items": {"type": "string"}}},
                    "required": ["name", "command"]},
        handler=lambda name, command, args=None:
            mcp.connect(name, command, args),
    ))
