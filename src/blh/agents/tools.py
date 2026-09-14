"""agents 工具注册:task + 7 个 Lead 团队工具。"""

from ..tools.registry import Tool, ToolRegistry


def register_agent_tools(registry: ToolRegistry, subagent, team) -> None:
    registry.register(Tool(
        name="task",
        description="Run a subagent with fresh context and return its final text.",
        parameters={"type": "object",
                    "properties": {"prompt": {"type": "string"}},
                    "required": ["prompt"]},
        handler=lambda prompt: subagent.run(prompt),
    ))
    registry.register(Tool(
        name="spawn_teammate",
        description="Spawn a persistent teammate.",
        parameters={"type": "object",
                    "properties": {"name": {"type": "string"},
                                   "role": {"type": "string"},
                                   "prompt": {"type": "string"},
                                   "task_id": {"type": "string"},
                                   "require_plan": {"type": "boolean"}},
                    "required": ["name", "role", "prompt"]},
        handler=team.spawn_teammate,
    ))
    registry.register(Tool(
        name="list_teammates",
        description="List active teammates.",
        parameters={"type": "object", "properties": {}},
        handler=team.list_teammates,
    ))
    registry.register(Tool(
        name="send_message",
        description="Message a teammate.",
        parameters={"type": "object",
                    "properties": {"to": {"type": "string"},
                                   "content": {"type": "string"}},
                    "required": ["to", "content"]},
        handler=team.lead_send_message,
    ))
    registry.register(Tool(
        name="request_shutdown",
        description="Ask a teammate to shut down.",
        parameters={"type": "object",
                    "properties": {"teammate": {"type": "string"}},
                    "required": ["teammate"]},
        handler=team.request_shutdown,
    ))
    registry.register(Tool(
        name="request_plan",
        description="Require a teammate plan before workspace changes.",
        parameters={"type": "object",
                    "properties": {"teammate": {"type": "string"},
                                   "task": {"type": "string"}},
                    "required": ["teammate", "task"]},
        handler=team.request_plan,
    ))
    registry.register(Tool(
        name="review_plan",
        description="Approve or reject a plan.",
        parameters={"type": "object",
                    "properties": {"request_id": {"type": "string"},
                                   "approve": {"type": "boolean"},
                                   "feedback": {"type": "string"}},
                    "required": ["request_id", "approve"]},
        handler=team.review_plan,
    ))
    registry.register(Tool(
        name="create_worktree",
        description="Create and bind a task worktree.",
        parameters={"type": "object",
                    "properties": {"name": {"type": "string"},
                                   "task_id": {"type": "string"}},
                    "required": ["name", "task_id"]},
        handler=team.create_worktree,
    ))
