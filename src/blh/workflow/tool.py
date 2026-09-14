"""Workflow 工具:校验、预留 runId、上锁、执行、落盘。"""

import asyncio
import json
import os
import re
import secrets
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .journal import WorkflowJournal
from .runtime import Budget, ExecutionState
from .schema import WorkflowInputError

WORKFLOW_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
RUN_ID_RE = re.compile(r"^wf_[A-Za-z0-9][A-Za-z0-9._-]{0,63}_[0-9a-f]{16}$")


def create_run_id(meta) -> str:
    return f"wf_{meta['name']}_{secrets.token_hex(8)}"


def create_task_id(run_id) -> str:
    return f"local_workflow_{run_id}"


def validate_meta(meta):
    if not isinstance(meta, dict):
        raise WorkflowInputError("meta must be an object literal")
    if not meta.get("name") or not meta.get("description"):
        raise WorkflowInputError("meta requires `name` and `description`")
    if not isinstance(meta["name"], str) or not WORKFLOW_NAME_RE.fullmatch(meta["name"]):
        raise WorkflowInputError(
            "meta.name must be a 1-64 character slug using letters, numbers, '.', '_', or '-'")
    if not isinstance(meta["description"], str):
        raise WorkflowInputError("meta.description must be a string")
    return meta


@dataclass
class WorkflowTask:
    task_id: str
    run_id: str
    meta: dict
    status: str = "running"
    usage: dict = field(default_factory=lambda: {"agents": 0, "tokens": 0})
    progress: list = field(default_factory=list)

    def progress_event(self, ptype, **data):
        self.progress.append({"type": ptype, **data})


_lock_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


@contextmanager
def workflow_run_lock(run_id: str):
    """进程内互斥:同一 run 只允许一个活跃执行。"""
    with _lock_guard:
        lock = _locks.setdefault(run_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise WorkflowInputError(f"workflow run {run_id} is already active")
    try:
        yield
    finally:
        lock.release()
        with _lock_guard:
            if not lock.locked() and _locks.get(run_id) is lock:
                _locks.pop(run_id, None)


def serialize_task(task):
    return {
        "taskId": task.task_id,
        "taskType": "local_workflow",
        "runId": task.run_id,
        "workflowName": task.meta["name"],
        "status": task.status,
        "usage": dict(task.usage),
        "progress": list(task.progress),
    }


class WorkflowTool:
    def __init__(self, store, runner_factory, workflows):
        self.store = Path(store)
        self.runner_factory = runner_factory
        self.workflows = workflows

    async def call(self, meta, script_fn, args=None, resume_from_run_id=None):
        validate_meta(meta)
        resuming = resume_from_run_id is not None
        if resuming:
            run_id = self._validate_run_id(resume_from_run_id)
        else:
            run_id = self._reserve_run_id(meta)
        with workflow_run_lock(run_id):
            return await self._call_locked(meta, script_fn, args, run_id, resuming)

    async def _call_locked(self, meta, script_fn, args, run_id, resuming):
        if resuming:
            snapshot = self._read_snapshot(run_id)
            if snapshot.get("workflowName") != meta["name"]:
                raise WorkflowInputError("resume runId does not match workflow meta")
            saved_args = snapshot.get("args", {})
            if args is None:
                args = saved_args
            elif args != saved_args:
                raise WorkflowInputError("resume args do not match the original run")
            journal = WorkflowJournal(run_id, resume=True, store=self.store)
        else:
            args = args or {}
            journal = WorkflowJournal(run_id, resume=False, store=self.store)

        task_id = create_task_id(run_id)
        task = WorkflowTask(task_id, run_id, meta)
        launched = {"status": "async_launched", "taskId": task_id,
                    "taskType": "local_workflow", "runId": run_id,
                    "workflowName": meta["name"]}
        self._write_json(self.store / f"{run_id}.json", {
            "runId": run_id, "workflowName": meta["name"], "args": args,
            "task": serialize_task(task)})

        try:
            ctx = ExecutionState(task, journal, self.runner_factory(),
                                 Budget(args.get("budget")), args,
                                 workflows=self.workflows)
            result = await script_fn(ctx, args)
            task.status = "completed"
        except Exception as error:  # noqa: BLE001 - 失败/停止都关闭本 run
            task.status = "failed"
            result = {"error": str(error)}
        finally:
            journal.close()

        self._write_json(self.store / f"{run_id}.output.json", result)
        self._write_json(self.store / f"{run_id}.json", {
            "runId": run_id, "workflowName": meta["name"], "args": args,
            "task": serialize_task(task)})
        self._save_last_run(run_id)
        return {"launched": launched, "result": result, "task": task}

    def _reserve_run_id(self, meta):
        self.store.mkdir(parents=True, exist_ok=True)
        for _ in range(32):
            run_id = self._validate_run_id(create_run_id(meta))
            snapshot_path = self.store / f"{run_id}.json"
            try:
                fd = os.open(snapshot_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                continue
            os.close(fd)
            return run_id
        raise WorkflowInputError("could not allocate a unique workflow runId")

    @staticmethod
    def _validate_run_id(run_id):
        if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
            raise WorkflowInputError("invalid workflow runId")
        return run_id

    def _write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, default=str),
                             encoding="utf-8")
        os.replace(temporary, path)

    def _read_snapshot(self, run_id):
        path = self.store / f"{run_id}.json"
        if not path.exists():
            raise WorkflowInputError(f"resume snapshot not found for {run_id}")
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WorkflowInputError(f"invalid resume snapshot for {run_id}") from exc
        if not isinstance(snapshot, dict):
            raise WorkflowInputError(f"invalid resume snapshot for {run_id}")
        return snapshot

    def _save_last_run(self, run_id):
        (self.store / "last_run.txt").write_text(run_id, encoding="utf-8")


async def run_workflow(name, args=None, resume_from_run_id=None,
                       store=None, runner_factory=None, workflows=None):
    if not isinstance(name, str):
        raise WorkflowInputError("workflow name must be a string")
    if workflows is None or name not in workflows:
        raise WorkflowInputError(f"unknown workflow '{name}'")
    if args is not None and not isinstance(args, dict):
        raise WorkflowInputError("workflow args must be an object")
    meta, script_fn = workflows[name]
    out = await WorkflowTool(store, runner_factory, workflows).call(
        meta, script_fn, args=args, resume_from_run_id=resume_from_run_id)
    return {"launched": out["launched"], "result": out["result"],
            "task": serialize_task(out["task"])}


def run_workflow_sync(name, args=None, resume_from_run_id=None,
                      store=None, runner_factory=None, workflows=None):
    """同步桥接:asyncio.run 驱动异步编排,异常转字符串。"""
    try:
        return json.dumps(asyncio.run(
            run_workflow(name, args=args, resume_from_run_id=resume_from_run_id,
                         store=store, runner_factory=runner_factory,
                         workflows=workflows)), default=str)
    except WorkflowInputError as exc:
        return f"Error: {exc}"
