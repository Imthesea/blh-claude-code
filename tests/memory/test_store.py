import pytest

from blh.memory.store import MEMORY_TYPES, MemoryStore


def make_store(tmp_path):
    return MemoryStore(tmp_path / ".memory")


def test_parse_frontmatter_roundtrip():
    text = ("---\nname: user-preference-tabs\n"
            "description: User prefers tabs\ntype: user\n---\n\nBody here.\n")
    meta, body = MemoryStore.parse_frontmatter(text)
    assert meta == {"name": "user-preference-tabs",
                    "description": "User prefers tabs", "type": "user"}
    assert body == "Body here.\n"


def test_parse_frontmatter_missing_returns_empty():
    meta, body = MemoryStore.parse_frontmatter("just body\n")
    assert meta == {}
    assert body == "just body\n"


def test_parse_frontmatter_invalid_yaml_returns_original():
    text = "---\nname: [unclosed\n---\nbody\n"
    meta, body = MemoryStore.parse_frontmatter(text)
    assert meta == {}
    assert body == text


def test_memory_slug_normalizes():
    assert MemoryStore.memory_slug("User Preference: Tabs!") == "user-preference-tabs"
    assert MemoryStore.memory_slug("   ") == "memory"


def test_memory_path_rejects_escape(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.memory_path("../evil.md")
    with pytest.raises(ValueError):
        store.memory_path("sub/evil.md")


def test_memory_path_rejects_index_as_record(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.memory_path("MEMORY.md")
    assert store.memory_path("MEMORY.md", allow_index=True).name == "MEMORY.md"


def test_memory_types_constant():
    assert MEMORY_TYPES == ("user", "feedback", "project", "reference")
