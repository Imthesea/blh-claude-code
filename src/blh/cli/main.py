import argparse
from pathlib import Path

from ..compaction.compactor import ContextCompactor
from ..compaction.tools import register_compact_tool
from ..core.config import load_config
from ..core.harness import Harness
from ..core.hooks import PRE_TOOL_USE, HookBus
from ..core.loop import last_assistant_text
from ..memory.store import MemoryStore
from ..memory.system import Memory
from ..planning.tasks import TaskStore
from ..planning.todo import TodoManager
from ..planning.tools import register_planning_tools
from ..providers.openai import OpenAIProvider
from ..security.approval import make_permission_hook
from ..security.rules import DEFAULT_RULES
from ..tools import register_builtin_tools
from ..tools.registry import ToolRegistry
from .repl import repl


def build_harness(workdir: str | None = None) -> Harness:
    config = load_config(workdir)
    provider = OpenAIProvider(config)
    tools = ToolRegistry()
    register_builtin_tools(tools, config)
    register_compact_tool(tools)
    wd = Path(config.workdir)
    todo_manager = TodoManager()
    task_store = TaskStore(wd / ".tasks")
    register_planning_tools(tools, todo_manager, task_store)
    memory = Memory(MemoryStore(wd / ".memory"), provider)
    compactor = ContextCompactor(
        provider,
        transcript_dir=wd / ".transcripts",
        tool_results_dir=wd / ".task_outputs" / "tool-results",
    )
    hooks = HookBus()
    hooks.register(
        PRE_TOOL_USE, make_permission_hook(DEFAULT_RULES, config.workdir))
    return Harness(config, provider, tools, hooks, compactor, todo_manager, memory)


def main() -> None:
    parser = argparse.ArgumentParser(prog="blh")
    parser.add_argument("-p", "--print", dest="prompt",
                        help="run a single prompt and print the reply")
    args = parser.parse_args()

    harness = build_harness()
    if args.prompt:
        messages = harness.new_session()
        harness.run_turn(messages, args.prompt)
        print(last_assistant_text(messages))
    else:
        repl(harness)


if __name__ == "__main__":
    main()
