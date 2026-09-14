import subprocess
from pathlib import Path

import pytest

from blh.agents.worktree import (
    create_worktree,
    remove_worktree,
    task_cwd,
    validate_worktree_name,
    worktree_branch,
    worktree_path,
)
from blh.planning.tasks import TaskStore


def _git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True,
                   capture_output=True, text=True)


def _init_repo(path: Path):
    _git(path, "init")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Tester")
    (path / "f.txt").write_text("x", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")


def test_validate_worktree_name():
    assert validate_worktree_name("fix-1") is None
    assert validate_worktree_name("a/b") is not None
    assert validate_worktree_name("..") is not None
    assert validate_worktree_name("-x") is not None


def test_worktree_branch():
    assert worktree_branch("fix-1") == "wt/fix-1"


def test_worktree_path_rejects_escape(tmp_path):
    with pytest.raises(ValueError):
        worktree_path(tmp_path, "../etc")


def test_create_and_remove_worktree(tmp_path):
    _init_repo(tmp_path)
    store = TaskStore(tmp_path / ".tasks")
    task = store.create("ship feature")
    wt_dir = tmp_path / ".worktrees"
    result = create_worktree(store, str(tmp_path), wt_dir, "feat-1", task.id)
    assert "created" in result
    bound = store.load(task.id)
    assert bound.worktree == "feat-1"
    assert (wt_dir / "feat-1").is_dir()
    assert task_cwd(bound, str(tmp_path), wt_dir) == str((wt_dir / "feat-1").resolve())

    store.claim(task.id)
    store.complete(task.id)
    result = remove_worktree(store, str(tmp_path), wt_dir, "feat-1")
    assert "removed" in result
    assert store.load(task.id).worktree is None
