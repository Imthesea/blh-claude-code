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


def test_memory_document_has_frontmatter_and_body(tmp_path):
    store = make_store(tmp_path)
    doc = store.memory_document("User Pref", "user", "Likes tabs", "Use tabs.")
    assert doc.startswith("---\n")
    assert "name: User Pref" in doc
    assert "type: user" in doc
    assert doc.endswith("Use tabs.\n")


def test_write_memory_file_and_index(tmp_path):
    store = make_store(tmp_path)
    path = store.write_memory_file("User Pref", "user", "Likes tabs", "Use tabs.")
    assert path.name == "user-pref.md"
    assert path.is_file()
    assert "[User Pref](user-pref.md) - Likes tabs" in store.read_memory_index()


def test_write_memory_file_rejects_invalid(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(ValueError):
        store.write_memory_file("", "user", "d", "b")
    with pytest.raises(ValueError):
        store.write_memory_file("n", "bad", "d", "b")
    with pytest.raises(ValueError):
        store.write_memory_file("n", "user", "", "b")


def test_read_memory_file(tmp_path):
    store = make_store(tmp_path)
    store.write_memory_file("N", "user", "D", "B")
    assert store.read_memory_file("n.md") is not None
    assert store.read_memory_file("missing.md") is None


def test_list_memory_files_skips_index(tmp_path):
    store = make_store(tmp_path)
    store.write_memory_file("A", "user", "desc a", "body a")
    store.write_memory_file("B", "project", "desc b", "body b")
    records = store.list_memory_files()
    assert [r["filename"] for r in records] == ["a.md", "b.md"]
    assert records[0]["type"] == "user"


def test_should_store_memory_scope_and_temporary(tmp_path):
    store = make_store(tmp_path)
    good = {"scope": "persistent", "type": "user", "name": "Pref",
            "description": "Likes tabs", "body": "Use tabs."}
    assert store.should_store_memory(good, [])
    assert not store.should_store_memory({**good, "scope": "current_task"}, [])
    assert not store.should_store_memory({**good, "type": "bad"}, [])
    assert not store.should_store_memory({**good, "body": ""}, [])
    assert not store.should_store_memory(
        {**good, "body": "do this in this session"}, [])


def test_should_store_memory_dedup(tmp_path):
    store = make_store(tmp_path)
    existing = [{"name": "Pref", "description": "Likes tabs", "body": "Use tabs."}]
    dup_slug = {"scope": "persistent", "type": "user", "name": "pref",
                "description": "other", "body": "other body"}
    dup_desc = {"scope": "persistent", "type": "user", "name": "Other",
                "description": "likes tabs", "body": "x"}
    dup_body = {"scope": "persistent", "type": "user", "name": "Other",
                "description": "y", "body": "use tabs."}
    assert not store.should_store_memory(dup_slug, existing)
    assert not store.should_store_memory(dup_desc, existing)
    assert not store.should_store_memory(dup_body, existing)
