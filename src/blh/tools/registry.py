import json
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema
    handler: Callable[..., str]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [
            {"type": "function",
             "function": {"name": t.name,
                          "description": t.description,
                          "parameters": t.parameters}}
            for t in self._tools.values()
        ]

    def dispatch(self, name: str, arguments_json: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"error: unknown tool '{name}'"
        try:
            args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as e:
            return f"error: invalid tool arguments: {e}"
        try:
            return tool.handler(**args)
        except Exception as e:  # noqa: BLE001 - tool errors are returned as strings to the model
            return f"error: tool '{name}' failed: {e}"
