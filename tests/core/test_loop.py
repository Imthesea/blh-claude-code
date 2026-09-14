import json

import pytest

from blh.compaction.compactor import ContextCompactor
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


def make_harness(scripted, tools=None, hooks=None, compactor=None):
    cfg = Config(api_key="k", base_url=None, model="m", workdir=".")
    reg = ToolRegistry()
    for t in (tools or []):
        reg.register(t)
    return Harness(cfg, MockProvider(scripted), reg, hooks or HookBus(), compactor)


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


def make_compactor(tmp_path, provider=None):
    return ContextCompactor(
        provider or MockProvider([]),
        transcript_dir=tmp_path / ".transcripts",
        tool_results_dir=tmp_path / ".task_outputs" / "tool-results",
    )


class FlakyProvider:
    """脚本元素为 Exception 时抛出,否则作为 assistant 消息返回。"""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        action = self.script.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


class FakePromptTooLong(Exception):
    status_code = 400


def test_run_turn_passes_active_request_to_prepare(tmp_path):
    seen = {}
    compactor = make_compactor(tmp_path)

    def fake_prepare(messages, request):
        seen["request"] = request
        return messages

    compactor.prepare = fake_prepare
    h = make_harness([text_msg("done")], compactor=compactor)
    messages = h.new_session()
    h.run_turn(messages, "fix the bug")
    assert seen["request"] == "fix the bug"


def test_agent_loop_reactive_compact_retries_once(tmp_path):
    provider = FlakyProvider([
        FakePromptTooLong("Error: prompt_too_long"),
        {"role": "assistant", "content": "summary of old", "tool_calls": None},
        text_msg("recovered"),
    ])
    # compactor 与 harness 共享同一 provider:摘要调用消耗同一脚本
    compactor = make_compactor(tmp_path, provider)
    h = make_harness([], compactor=compactor)
    h.provider = provider
    messages = h.new_session()
    h.run_turn(messages, "hi")
    assert provider.calls == 3
    assert last_assistant_text(messages) == "recovered"
    assert messages[0]["role"] == "system"
    assert messages[1]["content"].startswith("[Reactive compact]")


def test_agent_loop_reraises_after_retry_exhausted(tmp_path):
    provider = FlakyProvider([
        FakePromptTooLong("prompt_too_long"),
        {"role": "assistant", "content": "summary", "tool_calls": None},
        FakePromptTooLong("still prompt_too_long"),
    ])
    compactor = make_compactor(tmp_path, provider)
    h = make_harness([], compactor=compactor)
    h.provider = provider
    with pytest.raises(FakePromptTooLong):
        h.run_turn(h.new_session(), "hi")
    assert provider.calls == 3


def test_agent_loop_reraises_non_context_errors(tmp_path):
    provider = FlakyProvider([RuntimeError("boom")])
    compactor = make_compactor(tmp_path)
    h = make_harness([], compactor=compactor)
    h.provider = provider
    with pytest.raises(RuntimeError):
        h.run_turn(h.new_session(), "hi")
    assert provider.calls == 1


def test_agent_loop_compact_tool_compacts_after_batch(tmp_path):
    side_effects = []
    tools = [Tool("write_note", "", {"type": "object",
                                     "properties": {"text": {"type": "string"}}},
                  handler=lambda text: side_effects.append(text) or "noted")]
    batch = {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function",
         "function": {"name": "write_note", "arguments": json.dumps({"text": "hello"})}},
        {"id": "c2", "type": "function",
         "function": {"name": "compact", "arguments": "{}"}},
    ]}
    provider = MockProvider([
        batch,
        {"role": "assistant", "content": "conversation summary",
         "tool_calls": None},
        text_msg("done"),
    ])
    compactor = make_compactor(tmp_path, provider)
    h = make_harness([], tools=tools, compactor=compactor)
    h.provider = provider
    messages = h.new_session()
    h.run_turn(messages, "note then compact")
    # 同批 write_note 的副作用在压缩前完成,不丢失
    assert side_effects == ["hello"]
    assert len(messages) == 3  # system + [Compacted] 摘要 + 最终答复
    assert messages[0]["role"] == "system"
    assert messages[1]["content"].startswith("[Compacted]")
    assert "Current user request:\nnote then compact" in messages[1]["content"]
    assert "conversation summary" in messages[1]["content"]
    assert list((tmp_path / ".transcripts").glob("*.jsonl"))


def test_system_prompt_guards_compacted_messages():
    h = make_harness([])
    assert "Conversation summary" in h.system_prompt()
