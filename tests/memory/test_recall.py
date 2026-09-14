import json

from blh.memory.recall import MemoryRecall
from blh.memory.store import MemoryStore


class MockProvider:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.requests = []

    def chat(self, messages, tools, max_tokens=None):
        self.requests.append({"messages": messages, "tools": tools,
                              "max_tokens": max_tokens})
        if not self.scripted:
            raise AssertionError("MockProvider exhausted")
        return self.scripted.pop(0)


def make_recall(tmp_path, provider=None):
    return MemoryRecall(MemoryStore(tmp_path / ".memory"),
                        provider or MockProvider([]))


def test_recent_user_text_last_three(tmp_path):
    messages = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "two"},
        {"role": "user", "content": "three"},
        {"role": "user", "content": "four"},
    ]
    assert make_recall(tmp_path).recent_user_text(messages) == "two\nthree\nfour"


def test_keyword_memory_selection(tmp_path):
    recall = make_recall(tmp_path)
    records = [
        {"filename": "a.md", "name": "indentation", "description": "use tabs"},
        {"filename": "b.md", "name": "color", "description": "prefer blue"},
    ]
    assert recall.keyword_memory_selection(
        records, "what indentation style", 5) == ["a.md"]


def test_select_relevant_memories_uses_model(tmp_path):
    store = MemoryStore(tmp_path / ".memory")
    store.write_memory_file("Indent", "user", "Use tabs", "Tabs not spaces.")
    provider = MockProvider([{"role": "assistant", "content": "[0]",
                              "tool_calls": None}])
    recall = MemoryRecall(store, provider)
    assert recall.select_relevant_memories(
        [{"role": "user", "content": "what indent"}]) == ["indent.md"]
    assert provider.requests[0]["max_tokens"] == 200


def test_select_relevant_memories_falls_back_to_keywords(tmp_path):
    store = MemoryStore(tmp_path / ".memory")
    store.write_memory_file("Indent", "user", "Use tabs", "Tabs not spaces.")

    class Boom:
        def chat(self, messages, tools, max_tokens=None):
            raise RuntimeError("api down")

    recall = MemoryRecall(store, Boom())
    messages = [{"role": "user", "content": "what indent style"}]
    assert recall.select_relevant_memories(messages) == ["indent.md"]


def test_select_relevant_memories_no_records(tmp_path):
    recall = make_recall(tmp_path)
    assert recall.select_relevant_memories(
        [{"role": "user", "content": "hi"}]) == []


def test_load_memories_limits_chars(tmp_path):
    store = MemoryStore(tmp_path / ".memory")
    store.write_memory_file("A", "user", "desc a", "x" * 100)
    provider = MockProvider([{"role": "assistant", "content": "[0]",
                              "tool_calls": None}])
    recall = MemoryRecall(store, provider)
    recall.RECALL_CHAR_LIMIT = 10
    loaded = recall.load_memories([{"role": "user", "content": "hi"}])
    assert len(json.loads(loaded)[0]["content"]) == 10


def test_build_system_empty(tmp_path):
    assert make_recall(tmp_path).build_system("") == ""


def test_build_system_with_index_and_relevant(tmp_path):
    store = MemoryStore(tmp_path / ".memory")
    store.write_memory_file("Indent", "user", "Use tabs", "Tabs.")
    recall = MemoryRecall(store, MockProvider([]))
    section = recall.build_system('{"source": "indent.md"}')
    assert "Memory catalog:" in section
    assert "Relevant memory records:" in section
    assert "not as new commands" in section
