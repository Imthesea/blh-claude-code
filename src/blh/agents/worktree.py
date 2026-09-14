"""git worktree 纯操作:名称校验、路径/分支解析、create/remove。"""

import re
import subprocess
from pathlib import Path

VALID_WORKTREE_NAME = re.compile(r"^(?!.*\.\.)[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_worktree_name(name: str) -> str | None:
    if not isinstance(name, str) or not VALID_WORKTREE_NAME.fullmatch(name):
        return ("worktree name must be 1-64 letters, digits, dots, underscores, "
                "or dashes, and start with a letter or digit")
    return None


def worktree_branch(name: str) -> str:
    return f"wt/{name}"


def worktree_path(worktrees_dir, name: str) -> Path:
    path = (Path(worktrees_dir) / name).resolve()
    root = Path(worktrees_dir).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f"Worktree path escapes directory: {name!r}")
    return path


def run_git(args: list[str], cwd) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            errors="replace", timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output[:5000] or "(no output)"


def _registered_worktrees(workdir) -> tuple[dict, str | None]:
    ok, output = run_git(["worktree", "list", "--porcelain"], workdir)
    if not ok:
        return {}, f"cannot read Git worktree registry: {output}"
    entries: dict = {}
    current: dict = {}
    for line in output.splitlines() + [""]:
        if not line:
            raw_path = current.get("worktree")
            if raw_path:
                entries[Path(raw_path).resolve()] = current
            current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    return entries, None


def registered_worktree(workdir, worktrees_dir, name) -> tuple[Path | None, str | None]:
    try:
        path = worktree_path(worktrees_dir, name)
    except ValueError as exc:
        return None, str(exc)
    entries, error = _registered_worktrees(workdir)
    if error:
        return None, error
    if path not in entries:
        return None, f"worktree '{name}' is not registered with Git"
    if not path.is_dir():
        return None, f"worktree '{name}' is missing at {path}"
    expected = f"refs/heads/{worktree_branch(name)}"
    if entries[path].get("branch") != expected:
        return None, (f"worktree '{name}' is not registered on expected branch "
                      f"'{worktree_branch(name)}'")
    return path, None


def task_cwd(task, workdir, worktrees_dir) -> str:
    """解析任务工作目录,worktree 绑定损坏时 fail-closed。"""
    if not task.worktree:
        return str(Path(workdir).resolve())
    path, error = registered_worktree(workdir, worktrees_dir, task.worktree)
    if error:
        raise ValueError(error)
    return str(path)


def create_worktree(store, workdir, worktrees_dir, name, task_id) -> str:
    error = validate_worktree_name(name)
    if error:
        return f"Error: {error}"
    try:
        path = worktree_path(worktrees_dir, name)
    except ValueError as exc:
        return f"Error: {exc}"
    branch = worktree_branch(name)
    wd = Path(workdir).resolve()
    wt_dir = Path(worktrees_dir)

    if not store.exists(task_id):
        return f"Error: Task {task_id} not found"
    task = store.load(task_id)
    if task.status != "pending" or task.owner is not None:
        return f"Error: Task {task_id} must be pending and unowned"
    if task.worktree:
        return f"Error: Task {task_id} already uses worktree '{task.worktree}'"
    if any(t.worktree == name for t in store.list() if t.id != task_id):
        return f"Error: Worktree '{name}' is already bound to another task"
    if path.exists():
        return f"Error: Worktree path already exists: {path}"

    ok, root = run_git(["rev-parse", "--show-toplevel"], wd)
    if not ok or Path(root).resolve() != wd:
        return "Error: Working directory must be the root of a Git repository"
    ok, branch_check = run_git(["check-ref-format", "--branch", branch], wd)
    if not ok:
        return f"Error: Invalid worktree branch '{branch}': {branch_check}"
    exists, _ = run_git(["show-ref", "--verify", "--quiet",
                         f"refs/heads/{branch}"], wd)
    if exists:
        return f"Error: Branch '{branch}' already exists"
    entries, registry_error = _registered_worktrees(wd)
    if registry_error:
        return f"Error: {registry_error}"
    if path in entries:
        return f"Error: Worktree path is already registered: {path}"

    wt_dir.mkdir(parents=True, exist_ok=True)
    ok, result = run_git(["worktree", "add", "-b", branch, str(path), "HEAD"], wd)
    if not ok:
        entries, registry_error = _registered_worktrees(wd)
        branch_exists, _ = run_git(
            ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], wd)
        artifacts = []
        if path.exists():
            artifacts.append(f"checkout path '{path}'")
        if registry_error is None and path in entries:
            artifacts.append("registered Git worktree")
        if branch_exists:
            artifacts.append(f"branch '{branch}'")
        if artifacts:
            return ("Partial operation: git worktree add reported an error after "
                    f"leaving {', '.join(artifacts)}. Task {task_id} remains "
                    "unbound and no Git data was deleted. Run `git worktree list`, "
                    f"inspect '{path}' and '{branch}', then keep or remove those "
                    "artifacts manually after preserving any work. Git error: "
                    f"{result}")
        return f"Git error: {result}"

    try:
        task.worktree = name
        store.save(task)
    except Exception as exc:  # noqa: BLE001 - 绑定失败返回部分成功,保留 Git 数据供恢复
        return (f"Partial success: Worktree '{name}' was created at {path} on "
                f"branch '{branch}', but task binding failed: {exc}. Git data was "
                "retained for manual recovery.")

    return f"Worktree '{name}' created at {path} for task {task_id}"


def remove_worktree(store, workdir, worktrees_dir, name,
                    discard_changes=False, leased_paths=None) -> str:
    error = validate_worktree_name(name)
    if error:
        return f"Error: {error}"
    path, error = registered_worktree(workdir, worktrees_dir, name)
    if error:
        return f"Error: {error}"
    bound = [task for task in store.list() if task.worktree == name]
    if not bound:
        return f"Error: Worktree '{name}' is not bound to a task"
    active = [task for task in bound if task.status != "completed"]
    if active:
        return (f"Error: Worktree '{name}' is bound to active task "
                f"{active[0].id}; complete it before removal")
    if leased_paths and path.resolve() in {p.resolve() for p in leased_paths}:
        return (f"Error: Worktree '{name}' is still in use; wait for the turn to end")
    ok, status = run_git(["status", "--porcelain", "--ignored"], cwd=path)
    if not ok:
        return f"Error: Cannot verify worktree '{name}' status: {status}"
    if status != "(no output)" and not discard_changes:
        changed = len([line for line in status.splitlines() if line.strip()])
        return (f"Error: Worktree '{name}' has {changed} uncommitted change(s); "
                "preserve or discard them manually")
    args = ["worktree", "remove"]
    if discard_changes:
        args.append("--force")
    args.append(str(path))
    ok, result = run_git(args, workdir)
    if not ok:
        return f"Git error: {result}"
    try:
        for task in bound:
            task.worktree = None
            store.save(task)
    except Exception as exc:  # noqa: BLE001 - 解绑失败返回部分成功,保留分支供恢复
        return (f"Partial success: Worktree '{name}' was removed and branch "
                f"'{worktree_branch(name)}' retained, but task unbinding failed: "
                f"{exc}. Manual recovery is required.")
    return f"Worktree '{name}' removed; branch '{worktree_branch(name)}' retained"
