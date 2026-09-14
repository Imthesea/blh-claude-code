import argparse
from pathlib import Path

from ..agents.bus import MessageBus
from ..agents.subagent import SubagentRunner
from ..agents.team import TeamRuntime
from ..agents.tools import register_agent_tools
from ..compaction.compactor import ContextCompactor
from ..compaction.tools import register_compact_tool
from ..core.config import load_config
from ..core.harness import Harness
from ..core.hooks import PRE_TOOL_USE, HookBus
from ..core.loop import last_assistant_text
from ..extensions import Extensions
from ..extensions.mcp import MCPRegistry
from ..extensions.skills import SkillLoader
from ..extensions.tools import register_extension_tools
from ..goals.controller import GoalController
from ..goals.evaluator import PromptGoalEvaluator
from ..jobs.background import BackgroundManager
from ..jobs.cron import CronScheduler
from ..jobs.runtime import JobsRuntime
from ..jobs.tools import register_jobs_tools
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
from ..workflow.registry import WORKFLOWS
from ..workflow.runtime import OpenAIWorkflowRunner
from ..workflow.tools import register_workflow_tools
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
    cron = CronScheduler(wd / ".scheduled_tasks.json")
    cron.load()
    register_jobs_tools(tools, cron)
    jobs = JobsRuntime(
        BackgroundManager(config.workdir, config.bash_timeout,
                          config.max_output_chars),
        cron,
    )
    compactor = ContextCompactor(
        provider,
        transcript_dir=wd / ".transcripts",
        tool_results_dir=wd / ".task_outputs" / "tool-results",
    )
    hooks = HookBus()
    hooks.register(
        PRE_TOOL_USE, make_permission_hook(DEFAULT_RULES, config.workdir))
    agents = TeamRuntime(
        store=task_store,
        bus=MessageBus(wd / ".mailboxes"),
        agent_lock=jobs.agent_lock,
        workdir=config.workdir,
        worktrees_dir=wd / ".worktrees",
        provider=provider,
        config=config,
        hooks=hooks,
    )
    subagent = SubagentRunner(provider, config, hooks)
    register_agent_tools(tools, subagent, agents)
    skills = SkillLoader(wd / "skills")
    mcp = MCPRegistry(tools, config.workdir)
    register_extension_tools(tools, skills, mcp)
    extensions = Extensions(skills, mcp)
    workflow_store = wd / ".workflow_runtime"
    register_workflow_tools(
        tools, store=workflow_store,
        runner_factory=lambda: OpenAIWorkflowRunner(provider),
        workflows=WORKFLOWS)
    goal = GoalController(PromptGoalEvaluator(provider))
    return Harness(config, provider, tools, hooks, compactor, todo_manager,
                   memory, jobs, agents, extensions, goal, workflow_store)


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
