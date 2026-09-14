import json

from blh.agents.subagent import SubagentRunner
from blh.core.config import Config
from blh.core.hooks import HookBus


class MockProvider:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def chat(self, messages, tools, max_tokens=None):
        self.calls += 1
        if not self.scripted:
            raise AssertionError("MockProvider exhausted")
        return self.scripted.pop(0)


def tool_call_msg(call_id, name, args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def text_msg(text):
    return {"role": "assistant", "content": text, "tool_calls": None}


def make_runner(tmp_path, scripted, hooks=None):
    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    return SubagentRunner(MockProvider(scripted), cfg, hooks or HookBus())


def test_subagent_returns_final_text(tmp_path):
    runner = make_runner(tmp_path, [text_msg("done")])
    assert runner.run("do it") == "done"


def test_subagent_dispatches_tool_then_returns(tmp_path):
    runner = make_runner(tmp_path, [
        tool_call_msg("c1", "write_file", {"path": "note.txt", "content": "hello"}),
        text_msg("wrote"),
    ])
    assert runner.run("write a note") == "wrote"
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello"


def test_subagent_permission_hook_blocks(tmp_path):
    hooks = HookBus()
    hooks.register("PreToolUse", lambda e: "denied: no")
    runner = make_runner(tmp_path, [
        tool_call_msg("c1", "write_file", {"path": "note.txt", "content": "x"}),
        text_msg("ok"),
    ], hooks=hooks)
    assert runner.run("write") == "ok"
    assert not (tmp_path / "note.txt").exists()


def test_subagent_has_no_task_tool(tmp_path):
    runner = make_runner(tmp_path, [])
    names = {s["function"]["name"] for s in runner.tools.schemas()}
    assert names == {"bash", "read_file", "write_file", "edit_file", "glob"}


def test_subagent_hits_30_turn_limit(tmp_path):
    class EndlessProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools, max_tokens=None):
            self.calls += 1
            return tool_call_msg("c", "write_file", {"path": "x.txt", "content": "y"})

    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    runner = SubagentRunner(EndlessProvider(), cfg, HookBus())
    result = runner.run("loop forever")
    assert "30 turns" in result
    assert runner.provider.calls == 30
