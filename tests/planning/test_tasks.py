import pytest

from blh.planning.tasks import TaskStore


def make_store(tmp_path):
    return TaskStore(tmp_path / ".tasks")


def test_create_returns_task_and_persists(tmp_path):
    store = make_store(tmp_path)
    task = store.create("ship it")
    assert task.id.startswith("task_")
    assert task.subject == "ship it"
    assert task.status == "pending"
    assert (tmp_path / ".tasks" / f"{task.id}.json").is_file()


def test_create_rejects_empty_subject(tmp_path):
    with pytest.raises(ValueError):
        make_store(tmp_path).create("   ")


def test_load_roundtrip(tmp_path):
    store = make_store(tmp_path)
    task = store.create("a", "desc")
    assert store.load(task.id) == task


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        make_store(tmp_path).load("task_deadbeef")


def test_path_rejects_invalid_ids(tmp_path):
    store = make_store(tmp_path)
    for bad in ["../etc", "task_XYZ", "task_123", ""]:
        with pytest.raises(ValueError):
            store._path(bad)


def test_list_empty_and_sorted(tmp_path):
    store = make_store(tmp_path)
    assert store.list() == []
    b = store.create("b")
    a = store.create("a")
    ids = [t.id for t in store.list()]
    assert set(ids) == {a.id, b.id}
    assert ids == sorted(ids)
