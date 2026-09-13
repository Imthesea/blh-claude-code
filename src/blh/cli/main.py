import argparse

from ..core.config import load_config
from ..core.harness import Harness
from ..core.hooks import PRE_TOOL_USE, HookBus
from ..core.loop import last_assistant_text
from ..providers.openai import OpenAIProvider
from ..security.approval import make_permission_hook
from ..security.rules import DEFAULT_RULES
from ..tools import register_builtin_tools
from ..tools.registry import ToolRegistry
from .repl import repl


def build_harness(workdir: str | None = None) -> Harness:
    config = load_config(workdir)
    harness = Harness(config, OpenAIProvider(config), ToolRegistry(), HookBus())
    register_builtin_tools(harness.tools, config)
    harness.hooks.register(
        PRE_TOOL_USE, make_permission_hook(DEFAULT_RULES, config.workdir))
    return harness


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
