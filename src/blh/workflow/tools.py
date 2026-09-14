"""workflow 工具注册。"""

from ..tools.registry import Tool, ToolRegistry
from .tool import run_workflow_sync


def register_workflow_tools(registry: ToolRegistry, store, runner_factory,
                            workflows) -> None:
    registry.register(Tool(
        name="run_workflow",
        description="Run a saved workflow by name. Pass input in args.",
        parameters={"type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "args": {"type": "object"},
                        "resume_from_run_id": {"type": "string"},
                    },
                    "required": ["name"]},
        handler=lambda name, args=None, resume_from_run_id=None:
            run_workflow_sync(name, args=args,
                              resume_from_run_id=resume_from_run_id,
                              store=store, runner_factory=runner_factory,
                              workflows=workflows),
    ))
