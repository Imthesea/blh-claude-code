import json

from blh.core.config import Config
from blh.core.harness import Harness
from blh.core.hooks import PRE_TOOL_USE, HookBus
from blh.core.loop import last_assistant_text
from blh.security.approval import make_permission_hook
from blh.security.rules import DEFAULT_RULES
from blh.tools import register_builtin_tools
from blh.tools.registry import ToolRegistry


class MockProvider:
    def __init__(self, scripted):
        self.scripted = list(scripted)

    def chat(self, messages, tools):
        if not self.scripted:
            raise AssertionError("MockProvider exhausted")
        return self.scripted.pop(0)


def tool_call_msg(call_id, name, args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def text_msg(text):
    return {"role": "assistant", "content": text, "tool_calls": None}


def test_agent_writes_and_reads_file(tmp_path):
    """完整闭环:模型要求写文件 → 权限放行(自动 y)→ 读回 → 文本回复。"""
    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    hooks = HookBus()
    hooks.register(PRE_TOOL_USE,
                   make_permission_hook(DEFAULT_RULES, str(tmp_path),
                                        ask_fn=lambda prompt: "y"))
    tools = ToolRegistry()
    register_builtin_tools(tools, cfg)
    provider = MockProvider([
        tool_call_msg("c1", "write_file", {"path": "hello.txt", "content": "world"}),
        tool_call_msg("c2", "read_file", {"path": "hello.txt"}),
        text_msg("file created with content: world"),
    ])
    harness = Harness(cfg, provider, tools, hooks)

    messages = harness.new_session()
    harness.run_turn(messages, "create hello.txt containing 'world'")

    assert (tmp_path / "hello.txt").read_text() == "world"
    tool_results = [m for m in messages if m["role"] == "tool"]
    assert len(tool_results) == 2
    assert "world" in tool_results[1]["content"]
    assert last_assistant_text(messages) == "file created with content: world"


def test_agent_denied_by_permission(tmp_path):
    """bash 走 ask,用户拒绝 → 模型收到拒绝原因。"""
    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    hooks = HookBus()
    hooks.register(PRE_TOOL_USE,
                   make_permission_hook(DEFAULT_RULES, str(tmp_path),
                                        ask_fn=lambda prompt: "n"))
    tools = ToolRegistry()
    register_builtin_tools(tools, cfg)
    provider = MockProvider([
        tool_call_msg("c1", "bash", {"command": "echo hi"}),
        text_msg("understood, command was denied"),
    ])
    harness = Harness(cfg, provider, tools, hooks)

    messages = harness.new_session()
    harness.run_turn(messages, "run echo hi")

    tool_results = [m for m in messages if m["role"] == "tool"]
    assert len(tool_results) == 1
    assert tool_results[0]["content"] == "denied by user"
