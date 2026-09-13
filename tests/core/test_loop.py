import json

from blh.core.config import Config
from blh.core.harness import Harness
from blh.core.hooks import HookBus
from blh.core.loop import last_assistant_text
from blh.tools.registry import Tool, ToolRegistry


class MockProvider:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def chat(self, messages, tools):
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


def make_harness(scripted, tools=None, hooks=None):
    cfg = Config(api_key="k", base_url=None, model="m", workdir=".")
    reg = ToolRegistry()
    for t in (tools or []):
        reg.register(t)
    return Harness(cfg, MockProvider(scripted), reg, hooks or HookBus())


def test_loop_stops_on_plain_text():
    h = make_harness([text_msg("done")])
    messages = h.new_session()
    h.run_turn(messages, "hi")
    assert last_assistant_text(messages) == "done"
    assert h.provider.calls == 1


def test_loop_dispatches_tool_then_stops():
    h = make_harness(
        [tool_call_msg("c1", "echo", {"text": "hello"}), text_msg("finished")],
        tools=[Tool("echo", "", {"type": "object",
                                 "properties": {"text": {"type": "string"}}},
                    handler=lambda text: text)],
    )
    messages = h.new_session()
    h.run_turn(messages, "go")
    tool_results = [m for m in messages if m["role"] == "tool"]
    assert tool_results[0]["tool_call_id"] == "c1"
    assert tool_results[0]["content"] == "hello"
    assert last_assistant_text(messages) == "finished"


def test_pre_tool_use_hook_blocks_dispatch():
    hooks = HookBus()
    hooks.register("PreToolUse", lambda e: "denied: no")
    h = make_harness(
        [tool_call_msg("c1", "echo", {"text": "x"}), text_msg("ok")],
        tools=[Tool("echo", "", {}, handler=lambda: "SHOULD NOT RUN")],
        hooks=hooks,
    )
    messages = h.new_session()
    h.run_turn(messages, "go")
    tool_results = [m for m in messages if m["role"] == "tool"]
    assert tool_results[0]["content"] == "denied: no"


def test_new_session_starts_with_system_message():
    h = make_harness([])
    messages = h.new_session()
    assert messages[0]["role"] == "system"
    assert "blh" in messages[0]["content"]


def test_run_turn_triggers_user_prompt_submit_and_stop_hooks():
    events = []
    hooks = HookBus()
    hooks.register("UserPromptSubmit", lambda text: events.append(("submit", text)))
    hooks.register("Stop", lambda msgs: events.append(("stop", len(msgs))))
    h = make_harness([text_msg("done")], hooks=hooks)
    messages = h.new_session()
    h.run_turn(messages, "hi")
    assert events[0] == ("submit", "hi")
    assert events[1][0] == "stop"
