import json

from blh.memory.extract import MemoryExtractor
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


def make_extractor(tmp_path, provider=None):
    return MemoryExtractor(MemoryStore(tmp_path / ".memory"),
                           provider or MockProvider([]))


def test_dialogue_text_last_messages(tmp_path):
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    text = make_extractor(tmp_path).dialogue_text(messages)
    assert "user: hello" in text
    assert "assistant: hi there" in text


def test_validate_memory_record(tmp_path):
    extractor = make_extractor(tmp_path)
    good = {"name": "Pref", "type": "user", "description": "d",
            "body": "b", "scope": "persistent"}
    assert extractor.validate_memory_record(good, require_scope=True)["name"] == "Pref"
    assert extractor.validate_memory_record(
        {**good, "scope": "current_task"}, require_scope=True) is not None
    assert extractor.validate_memory_record(
        {**good, "scope": "weird"}, require_scope=True) is None
    assert extractor.validate_memory_record(
        {"name": "", "type": "user", "description": "d", "body": "b"}) is None
    assert extractor.validate_memory_record("not a dict") is None


def test_extract_memories_stores_persistent(tmp_path):
    store = MemoryStore(tmp_path / ".memory")
    provider = MockProvider([{"role": "assistant", "content": json.dumps([
        {"name": "Pref", "type": "user", "scope": "persistent",
         "description": "Likes tabs", "body": "Use tabs."},
    ]), "tool_calls": None}])
    extractor = MemoryExtractor(store, provider)
    messages = [{"role": "user", "content": "I prefer tabs"},
                {"role": "assistant", "content": "noted"}]
    assert extractor.extract_memories(messages) == 1
    assert store.read_memory_file("pref.md") is not None
    assert provider.requests[0]["max_tokens"] == 1000


def test_extract_memories_skips_current_task_scope(tmp_path):
    store = MemoryStore(tmp_path / ".memory")
    provider = MockProvider([{"role": "assistant", "content": json.dumps([
        {"name": "Temp", "type": "user", "scope": "current_task",
         "description": "d", "body": "b"},
    ]), "tool_calls": None}])
    extractor = MemoryExtractor(store, provider)
    assert extractor.extract_memories(
        [{"role": "user", "content": "x"},
         {"role": "assistant", "content": "y"}]) == 0
    assert store.list_memory_files() == []


def test_extract_memories_swallows_provider_error(tmp_path):
    store = MemoryStore(tmp_path / ".memory")

    class Boom:
        def chat(self, messages, tools, max_tokens=None):
            raise RuntimeError("api down")

    extractor = MemoryExtractor(store, Boom())
    assert extractor.extract_memories(
        [{"role": "user", "content": "hi"}]) == 0
