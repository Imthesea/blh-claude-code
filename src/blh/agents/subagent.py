"""SubagentRunner:同步嵌套 Agent Loop,只返回最终文本,无 task 工具。"""

import json

from ..core.hooks import POST_TOOL_USE, PRE_TOOL_USE
from ..tools import register_builtin_tools
from ..tools.registry import ToolRegistry

SUB_SYSTEM = (
    "You are a coding agent. Complete the given task, then return a concise "
    "final answer."
)
MAX_SUBAGENT_TURNS = 30


def _parse_args(arguments: str) -> dict:
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class SubagentRunner:
    def __init__(self, provider, config, hooks):
        self.provider = provider
        self.config = config
        self.hooks = hooks
        self.tools = ToolRegistry()
        register_builtin_tools(self.tools, config)

    def run(self, prompt: str) -> str:
        messages = [
            {"role": "system", "content": SUB_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        for _ in range(MAX_SUBAGENT_TURNS):
            assistant = self.provider.chat(messages, self.tools.schemas())
            messages.append(assistant)
            tool_calls = assistant.get("tool_calls") or []
            if not tool_calls:
                return assistant.get("content") or "(no summary)"
            for call in tool_calls:
                name = call["function"]["name"]
                arguments = call["function"].get("arguments") or "{}"
                call_id = call.get("id", "")
                event = {"name": name, "input": _parse_args(arguments),
                         "id": call_id}
                blocked = self.hooks.first_block(PRE_TOOL_USE, event)
                if blocked is not None:
                    result = blocked
                else:
                    result = self.tools.dispatch(name, arguments)
                    self.hooks.trigger(POST_TOOL_USE, event, result)
                messages.append({"role": "tool", "tool_call_id": call_id,
                                 "content": result})
        return "Subagent stopped after 30 turns without a final answer."
