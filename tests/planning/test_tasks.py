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


def test_update_dependencies_adds_edge(tmp_path):
    store = make_store(tmp_path)
    a = store.create("a")
    b = store.create("b")
    assert store.update_dependencies(b.id, [a.id]).blocked_by == [a.id]


def test_update_dependencies_rejects_missing_dep(tmp_path):
    store = make_store(tmp_path)
    b = store.create("b")
    with pytest.raises(ValueError):
        store.update_dependencies(b.id, ["task_deadbeef"])


def test_update_dependencies_rejects_self(tmp_path):
    store = make_store(tmp_path)
    a = store.create("a")
    with pytest.raises(ValueError):
        store.update_dependencies(a.id, [a.id])


def test_update_dependencies_rejects_cycle(tmp_path):
    store = make_store(tmp_path)
    a = store.create("a")
    b = store.create("b")
    store.update_dependencies(a.id, [b.id])
    with pytest.raises(ValueError):
        store.update_dependencies(b.id, [a.id])


def test_depends_on_transitive(tmp_path):
    store = make_store(tmp_path)
    a = store.create("a")
    b = store.create("b")
    c = store.create("c")
    store.update_dependencies(b.id, [a.id])
    store.update_dependencies(c.id, [b.id])
    assert store._depends_on(c.id, a.id)
    assert not store._depends_on(a.id, c.id)


def test_incomplete_dependencies_and_can_start(tmp_path):
    store = make_store(tmp_path)
    a = store.create("a")
    b = store.create("b")
    store.update_dependencies(b.id, [a.id])
    assert store.incomplete_dependencies(store.load(b.id)) == [a.id]
    assert not store.can_start(b.id)
    assert store.can_start(a.id)
    store.claim(a.id)
    store.complete(a.id)
    assert store.can_start(b.id)
    assert store.incomplete_dependencies(store.load(b.id)) == []


def test_claim_blocked_and_unblocked(tmp_path):
    store = make_store(tmp_path)
    a = store.create("a")
    b = store.create("b")
    store.update_dependencies(b.id, [a.id])
    assert "blocked by" in store.claim(b.id)
    assert store.claim(a.id) == f"Claimed {a.id}."


def test_claim_idempotent_and_completed(tmp_path):
    store = make_store(tmp_path)
    a = store.create("a")
    store.claim(a.id)
    assert "already in progress" in store.claim(a.id)
    store.complete(a.id)
    assert "already completed" in store.claim(a.id)


def test_complete_requires_claim(tmp_path):
    store = make_store(tmp_path)
    a = store.create("a")
    assert "claim it first" in store.complete(a.id)


def test_complete_owner_mismatch(tmp_path):
    store = make_store(tmp_path)
    a = store.create("a")
    store.claim(a.id, owner="alice")
    assert "owned by alice" in store.complete(a.id, owner="bob")
    assert store.complete(a.id, owner="alice") == f"Completed {a.id}."


def test_task_has_worktree_field():
    from blh.planning.tasks import Task
    task = Task(id="task_00000000", subject="s", description="",
                status="pending", owner=None, blocked_by=[])
    assert task.worktree is None


def test_task_worktree_roundtrips(tmp_path):
    store = make_store(tmp_path)
    task = store.create("s")
    task.worktree = "wt-1"
    store.save(task)
    assert store.load(task.id).worktree == "wt-1"
