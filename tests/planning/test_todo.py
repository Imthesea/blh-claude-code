import pytest

from blh.planning.todo import TodoManager


def test_update_replaces_items_and_renders():
    tm = TodoManager()
    result = tm.update([{"content": "write code", "status": "in_progress"}])
    assert result == "[~] write code"
    assert tm.items == [{"content": "write code", "status": "in_progress"}]


def test_render_empty():
    assert TodoManager().render() == "No todos."


def test_render_marks_by_status():
    tm = TodoManager()
    tm.update([
        {"content": "a", "status": "pending"},
        {"content": "b", "status": "in_progress"},
        {"content": "c", "status": "completed"},
    ])
    assert tm.render().splitlines() == ["[ ] a", "[~] b", "[x] c"]


def test_update_rejects_non_list():
    with pytest.raises(TypeError):
        TodoManager().update({"content": "a"})


def test_update_rejects_empty_content():
    with pytest.raises(ValueError):
        TodoManager().update([{"content": "  "}])


def test_update_rejects_bad_status():
    with pytest.raises(ValueError):
        TodoManager().update([{"content": "a", "status": "done"}])


def test_update_rejects_too_many():
    tm = TodoManager()
    with pytest.raises(ValueError):
        tm.update([{"content": str(i)} for i in range(21)])


def test_note_round_counts_and_resets():
    tm = TodoManager()
    assert tm.note_round(False) is None  # 1
    assert tm.note_round(False) is None  # 2
    assert tm.note_round(False) == "<reminder>Update your todos.</reminder>"
    assert tm.note_round(False) is None  # 重置后回到 1


def test_note_round_resets_on_used_todo():
    tm = TodoManager()
    tm.note_round(False)  # 1
    tm.note_round(False)  # 2
    assert tm.note_round(True) is None  # 重置
    assert tm.note_round(False) is None  # 1
