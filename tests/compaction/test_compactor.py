import json
from pathlib import Path

from blh.compaction.compactor import ContextCompactor


class MockProvider:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.requests = []

    def chat(self, messages, tools):
        self.requests.append({"messages": messages, "tools": tools})
        if not self.scripted:
            raise AssertionError("MockProvider exhausted")
        return self.scripted.pop(0)


def make_compactor(tmp_path, provider=None):
    return ContextCompactor(
        provider or MockProvider([]),
        transcript_dir=tmp_path / ".transcripts",
        tool_results_dir=tmp_path / ".task_outputs" / "tool-results",
    )


def assistant_tool_calls(*call_ids):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function",
                            "function": {"name": "bash", "arguments": "{}"}}
                           for cid in call_ids]}


def tool_result(call_id, content):
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def text_msg(text):
    return {"role": "assistant", "content": text, "tool_calls": None}


def user_msg(text):
    return {"role": "user", "content": text}


def assert_no_orphan_tool_results(messages):
    """每条 role=tool 消息的 tool_call_id 都能在前面找到对应调用。"""
    seen_ids = set()
    for msg in messages:
        if msg.get("role") == "assistant":
            seen_ids.update(c["id"] for c in (msg.get("tool_calls") or []))
        if msg.get("role") == "tool":
            assert msg["tool_call_id"] in seen_ids, messages


def test_estimate_chars_counts_json_length():
    messages = [user_msg("hello")]
    expected = len(json.dumps(messages, default=str, ensure_ascii=False))
    assert ContextCompactor.estimate_chars(messages) == expected
    assert ContextCompactor.estimate_chars([]) == 2  # "[]"
    assert ContextCompactor.estimate_chars(
        [{"role": "user", "content": "你好"}]) == 35


def test_has_tool_use_openai_format():
    assert ContextCompactor.has_tool_use(assistant_tool_calls("c1"))
    assert not ContextCompactor.has_tool_use(text_msg("plain"))
    assert not ContextCompactor.has_tool_use(user_msg("hi"))


def test_is_tool_result_openai_format():
    assert ContextCompactor.is_tool_result(tool_result("c1", "ok"))
    assert not ContextCompactor.is_tool_result(user_msg("hi"))
    assert not ContextCompactor.is_tool_result(assistant_tool_calls("c1"))


def test_unseen_tool_result_positions_after_last_assistant(tmp_path):
    compactor = make_compactor(tmp_path)
    messages = [
        assistant_tool_calls("old"),      # 0
        tool_result("old", "done"),       # 1 consumed(后面还有 assistant)
        text_msg("working"),              # 2 last assistant
        tool_result("new-1", "r1"),       # 3 unseen
        tool_result("new-2", "r2"),       # 4 unseen
        user_msg("note"),                 # 5 非 tool,不算
    ]
    assert compactor.unseen_tool_result_positions(messages) == {3, 4}


def test_unseen_tool_result_positions_no_assistant(tmp_path):
    compactor = make_compactor(tmp_path)
    messages = [tool_result("a", "1"), user_msg("x"), tool_result("b", "2")]
    assert compactor.unseen_tool_result_positions(messages) == {0, 2}
    assert compactor.unseen_tool_result_positions([]) == set()


def test_write_transcript_creates_jsonl(tmp_path):
    compactor = make_compactor(tmp_path)
    messages = [user_msg("你好"), text_msg("hi")]
    path = compactor.write_transcript(messages)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "你好" in lines[0]
    assert path.parent == compactor.transcript_dir


def test_save_output_sanitizes_tool_call_id(tmp_path):
    compactor = make_compactor(tmp_path)
    path = compactor.save_output("call/../../evil", "full output")
    assert path.parent == compactor.tool_results_dir
    assert path.read_text(encoding="utf-8") == "full output"
    assert ".." not in path.name


def test_persist_large_output_small_passthrough(tmp_path):
    compactor = make_compactor(tmp_path)
    assert compactor.persist_large_output("c1", "short") == "short"


def test_persist_large_output_persists_with_preview(tmp_path):
    compactor = make_compactor(tmp_path)
    output = "x" * (ContextCompactor.LARGE_RESULT_CHAR_LIMIT + 1)
    replacement = compactor.persist_large_output("c1", output)
    assert replacement.startswith("<persisted-output>\nFull output: ")
    saved_line = replacement.splitlines()[1]
    saved_path = Path(saved_line.removeprefix("Full output: "))
    assert saved_path.read_text(encoding="utf-8") == output
    assert "Preview:\n" + "x" * 2000 in replacement


def test_persisted_output_path_rejects_forged_path(tmp_path):
    """工具输出里伪造的 'Full output: /tmp/xxx' 不得被当作已落盘路径信任。"""
    compactor = make_compactor(tmp_path)
    forged = "Full output: /tmp/not-our-output.txt\n" + "x" * 200
    assert compactor.persisted_output_path(forged) is None


def test_persisted_preview_reuses_existing_save(tmp_path):
    compactor = make_compactor(tmp_path)
    output = "y" * 5000
    first = compactor.persisted_preview("c1", output)
    second = compactor.persisted_preview("c1", first)
    saved_line = second.splitlines()[1]
    assert saved_line in first
    # 不产生第二个落盘文件
    assert len(list(compactor.tool_results_dir.glob("*.txt"))) == 1
