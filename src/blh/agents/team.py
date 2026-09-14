"""TeamRuntime:组合 MessageBus/TeammateRuntime/协议/assignment/plan gate。"""

import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .bus import is_valid_agent_name
from .teammate import TeammateRuntime
from .worktree import create_worktree as create_worktree_op
from .worktree import task_cwd as task_cwd_op

RESERVED_TEAMMATE_NAMES = {"lead", "agent"}
IDLE_SCAN_INTERVAL = 2.0


@dataclass
class ProtocolState:
    request_id: str
    type: str
    sender: str
    target: str
    status: str
    payload: str
    work_version: int | None = None
    task_id: str | None = None
    created_at: float = field(default_factory=time.time)


class TeamRuntime:
    def __init__(self, *, store, bus, agent_lock, workdir, worktrees_dir,
                 provider, config, hooks):
        self.store = store
        self.bus = bus
        self.agent_lock = agent_lock
        self.workdir = workdir
        self.worktrees_dir = Path(worktrees_dir)
        self.provider = provider
        self.config = config
        self.hooks = hooks
        self._team_lock = threading.RLock()
        self._team_turn = None
        self._lead_thread = None
        self._started = False
        self._stop = threading.Event()
        self.active_teammates: dict[str, str] = {}
        self.plan_gates: dict[str, str] = {}
        self.plan_request_ids: dict[str, str] = {}
        self.pending_requests: dict[str, ProtocolState] = {}
        self.assignments: dict[str, dict] = {}
        self.assignment_versions: dict[str, int] = {}
        self.threads: dict[str, threading.Thread] = {}

    # ---- 生命周期 ----
    def set_team_turn(self, callback):
        self._team_turn = callback

    def start(self):
        if self._started:
            return
        self._stop.clear()
        self._started = True
        self._lead_thread = threading.Thread(
            target=self._lead_inbox_loop, name="lead-inbox-processor", daemon=True)
        self._lead_thread.start()

    def stop(self):
        if not self._started:
            return
        self._stop.set()
        with self._team_lock:
            names = list(self.active_teammates)
        for name in names:
            self.request_shutdown(name)
        for name in names:
            thread = self.threads.get(name)
            if thread:
                thread.join(timeout=1)
        if self._lead_thread:
            self._lead_thread.join(timeout=1)
        self._started = False

    def _lead_inbox_loop(self):
        while not self._stop.wait(0.2):
            if not self.bus.peek("lead"):
                continue
            if not self.agent_lock.acquire(blocking=False):
                continue
            try:
                if self._team_turn is not None:
                    self._team_turn()
            finally:
                self.agent_lock.release()

    # ---- bus 委托(teammate 侧) ----
    def read_inbox(self, name):
        return self.bus.read_inbox(name)

    def wait_for_messages(self, name, timeout=None):
        return self.bus.wait_for_messages(name, timeout)

    # ---- assignment / 任务 ----
    def assignment_cwd(self, owner):
        assignment = self.assignments.get(owner)
        task = self._owner_in_progress(owner)
        if task and (not assignment or assignment.get("task_id") != task.id):
            cwd = self._task_cwd(task)
            assignment = {"task_id": task.id, "cwd": cwd}
            self.assignments[owner] = assignment
        elif not assignment:
            raise ValueError("Claim a Task before using workspace tools.")
        task = self.store.load(str(assignment["task_id"]))
        if task.status not in {"in_progress", "completed"} or task.owner != owner:
            raise ValueError(f"Assignment for {owner} is no longer active")
        cwd = self._task_cwd(task)
        if Path(cwd).resolve() != Path(assignment["cwd"]).resolve():
            raise ValueError(f"Assignment cwd changed for task {task.id}")
        return cwd

    def _owner_in_progress(self, owner):
        for task in self.store.list():
            if task.status == "in_progress" and task.owner == owner:
                return task
        return None

    def _task_cwd(self, task):
        return task_cwd_op(task, self.workdir, self.worktrees_dir)

    def claim_task(self, owner, task_id):
        with self._team_lock:
            if self.assignments.get(owner) or self._owner_in_progress(owner):
                return "Owner must complete its current task first"
            try:
                result = self.store.claim(task_id, owner=owner)
            except (ValueError, FileNotFoundError) as exc:
                return f"Error: {exc}"
            if result.startswith("Claimed "):
                task = self.store.load(task_id)
                cwd = self._task_cwd(task)
                self.assignments[owner] = {"task_id": task.id, "cwd": cwd}
                self._bump_version(owner)
            return result

    def complete_task(self, owner, task_id):
        with self._team_lock:
            try:
                return self.store.complete(task_id, owner=owner)
            except (ValueError, FileNotFoundError) as exc:
                return f"Error: {exc}"

    def list_tasks(self):
        return self.store.list()

    def _scan_unclaimed(self):
        ready = []
        for task in self.store.list():
            if task.status != "pending" or task.owner is not None:
                continue
            if not self.store.can_start(task.id):
                continue
            try:
                self._task_cwd(task)
            except ValueError:
                continue
            ready.append(task)
        return ready

    def claim_next_task(self, name):
        with self._team_lock:
            if self.assignments.get(name) or self._owner_in_progress(name):
                return None
            for task in self._scan_unclaimed():
                result = self.claim_task(name, task.id)
                if result.startswith("Claimed "):
                    return self.store.load(task.id)
        return None

    def _bump_version(self, owner):
        self.assignment_versions[owner] = self.assignment_versions.get(owner, 0) + 1
        if owner in self.plan_gates and self.plan_gates[owner] != "not_required":
            self.plan_gates[owner] = "required"
        self.plan_request_ids.pop(owner, None)

    def _current_work_identity(self, owner):
        assignment = self.assignments.get(owner)
        task_id = str(assignment["task_id"]) if assignment else None
        return self.assignment_versions.get(owner, 0), task_id

    def release_completed(self, owner):
        with self._team_lock:
            assignment = self.assignments.get(owner)
            if not assignment:
                return
            task = self.store.load(str(assignment["task_id"]))
            if task.status != "completed" or task.owner != owner:
                return
            self.assignments.pop(owner, None)
            self._bump_version(owner)
            self.plan_gates[owner] = "not_required"

    def finish_teammate(self, owner):
        with self._team_lock:
            task = self._owner_in_progress(owner)
            if task:
                task.status = "pending"
                task.owner = None
                self.store.save(task)
            self.assignments.pop(owner, None)
            self._bump_version(owner)
            self.plan_gates.pop(owner, None)
            self.plan_request_ids.pop(owner, None)
            self.active_teammates.pop(owner, None)
            self.threads.pop(owner, None)

    # ---- 协议(teammate 侧) ----
    def send_message(self, from_name, to, content, msg_type="message", metadata=None):
        with self._team_lock:
            if to != "lead" and to not in self.active_teammates:
                return f"Agent '{to}' is not active"
        self.bus.send(from_name, to, content, msg_type, metadata)
        return f"Sent to {to}"

    def submit_plan(self, from_name, plan):
        with self._team_lock:
            assignment = self.assignments.get(from_name)
            task_id = str(assignment["task_id"]) if assignment else None
            work_version = self.assignment_versions.get(from_name, 0)
            if self.plan_gates.get(from_name) == "pending":
                return "A plan is already waiting for review."
            request_id = self._new_request_id()
            self.pending_requests[request_id] = ProtocolState(
                request_id=request_id, type="plan_approval", sender=from_name,
                target="lead", status="pending", payload=plan,
                work_version=work_version, task_id=task_id)
            self.plan_gates[from_name] = "pending"
            self.plan_request_ids[from_name] = request_id
            self.active_teammates[from_name] = "waiting_approval"
        self.bus.send(from_name, "lead", plan, "plan_approval_request",
                      {"request_id": request_id})
        return f"Plan submitted ({request_id}). Wait for Lead's decision."

    def get_plan_gate(self, name):
        return self.plan_gates.get(name, "not_required")

    def set_active(self, name, status):
        with self._team_lock:
            self.active_teammates[name] = status

    def apply_shutdown_request(self, name, msg):
        request_id = msg.get("metadata", {}).get("request_id", "")
        with self._team_lock:
            state = self.pending_requests.get(request_id)
            valid = (
                msg.get("from") == "lead" and msg.get("to") == name
                and state is not None and state.type == "shutdown"
                and state.sender == "lead" and state.target == name
                and state.status == "pending"
                and self.active_teammates.get(name) != "stopping")
            if not valid:
                return False, "[Ignored shutdown request: request mismatch]"
            self.active_teammates[name] = "stopping"
        return True, request_id

    def apply_plan_response(self, name, msg):
        metadata = msg.get("metadata", {})
        request_id = metadata.get("request_id", "")
        work_version, task_id = self._current_work_identity(name)
        with self._team_lock:
            state = self.pending_requests.get(request_id)
            expected_id = self.plan_request_ids.get(name)
            valid = (
                msg.get("from") == "lead" and msg.get("to") == name
                and request_id == expected_id and state is not None
                and state.type == "plan_approval" and state.sender == name
                and state.target == "lead" and state.work_version == work_version
                and state.task_id == task_id
                and state.status in {"approved", "rejected"}
                and metadata.get("approve", False) == (state.status == "approved"))
            if not valid:
                return False, "[Ignored plan response: request mismatch]"
            self.plan_gates[name] = state.status
            self.active_teammates[name] = "working"
            self.plan_request_ids.pop(name, None)
            outcome = state.status
        return True, f"[Plan {outcome}] {msg['content']}"

    # ---- 协议(lead 侧) ----
    def _new_request_id(self):
        while True:
            request_id = f"req_{random.randint(0, 999999):06d}"
            if request_id not in self.pending_requests:
                return request_id

    def spawn_teammate(self, name, role, prompt, task_id=None, require_plan=False):
        if not is_valid_agent_name(name):
            return "Invalid teammate name: use 1-64 letters, digits, underscores, or dashes"
        if name.lower() in RESERVED_TEAMMATE_NAMES:
            return f"Invalid teammate name: '{name}' is reserved by the runtime"
        with self._team_lock:
            if any(existing.casefold() == name.casefold()
                   for existing in self.active_teammates):
                return f"Teammate '{name}' already exists"
            self.active_teammates[name] = "working"
            self.plan_gates[name] = "required" if require_plan else "not_required"
            self.assignment_versions[name] = 0
        if task_id:
            claimed = self.claim_task(name, task_id)
            if not claimed.startswith("Claimed "):
                with self._team_lock:
                    self.active_teammates.pop(name, None)
                    self.plan_gates.pop(name, None)
                    self.assignment_versions.pop(name, None)
                return f"Cannot spawn teammate '{name}': {claimed}"
        runtime = TeammateRuntime(
            name=name, role=role, prompt=prompt, task_id=task_id,
            require_plan=require_plan, provider=self.provider, config=self.config,
            hooks=self.hooks, store=self.store, team=self)
        thread = threading.Thread(target=runtime.run, daemon=True)
        with self._team_lock:
            self.threads[name] = thread
        thread.start()
        assigned = f" for {task_id}" if task_id else " without an initial Task"
        return (f"Teammate '{name}' spawned as {role}{assigned}. "
                "End this turn; the runtime will deliver its events.")

    def list_teammates(self):
        with self._team_lock:
            if not self.active_teammates:
                return "No active teammates."
            return "\n".join(f"{name}: {status}" for name, status in
                             sorted(self.active_teammates.items()))

    def lead_send_message(self, to, content):
        with self._team_lock:
            if to not in self.active_teammates:
                return f"Teammate '{to}' is not active"
        self.bus.send("lead", to, content)
        return f"Sent to {to}"

    def request_shutdown(self, teammate):
        with self._team_lock:
            if teammate not in self.active_teammates:
                return f"Teammate '{teammate}' is not active"
            request_id = self._new_request_id()
            self.pending_requests[request_id] = ProtocolState(
                request_id=request_id, type="shutdown", sender="lead",
                target=teammate, status="pending", payload="")
        self.bus.send("lead", teammate, "Finish the current step and shut down.",
                      "shutdown_request", {"request_id": request_id})
        return f"Shutdown requested from {teammate} ({request_id})"

    def request_plan(self, teammate, task):
        with self._team_lock:
            if teammate not in self.active_teammates:
                return f"Teammate '{teammate}' is not active"
            self.plan_gates[teammate] = "required"
        self.bus.send("lead", teammate, task, "plan_request")
        return f"Plan requested from {teammate}"

    def review_plan(self, request_id, approve, feedback=""):
        with self._team_lock:
            state = self.pending_requests.get(request_id)
            if not state:
                return f"Request {request_id} not found"
            if state.type != "plan_approval":
                return f"Request {request_id} is not a plan"
            if state.status != "pending":
                return f"Request {request_id} already {state.status}"
            work_version, task_id = self._current_work_identity(state.sender)
            if state.work_version != work_version or state.task_id != task_id:
                return f"Request {request_id} belongs to an earlier assignment"
            if self.plan_request_ids.get(state.sender) != request_id:
                return f"Request {request_id} is not the current plan"
            state.status = "approved" if approve else "rejected"
            sender = state.sender
        content = feedback or ("Plan approved." if approve
                               else "Revise the plan and submit it again.")
        self.bus.send("lead", sender, content, "plan_approval_response",
                      {"request_id": request_id, "approve": approve})
        return f"Plan {state.status} ({request_id})"

    def create_worktree(self, name, task_id):
        with self._team_lock:
            return create_worktree_op(self.store, self.workdir,
                                      self.worktrees_dir, name, task_id)

    # ---- lead 收件箱消费 ----
    def consume_and_inject_team(self, messages):
        msgs = self.bus.read_inbox("lead")
        for msg in msgs:
            metadata = msg.get("metadata", {})
            request_id = metadata.get("request_id", "")
            if request_id and msg.get("type", "").endswith("_response"):
                self._match_response(msg["type"], request_id,
                                     metadata.get("approve", False),
                                     msg.get("from", ""), msg.get("to", ""))
        if not msgs:
            return 0
        messages.append({"role": "user", "content": self._format_team_events(msgs)})
        return len(msgs)

    def _match_response(self, response_type, request_id, approve, from_agent, to_agent):
        with self._team_lock:
            state = self.pending_requests.get(request_id)
            if not state:
                return
            expected = {"shutdown": "shutdown_response",
                        "plan_approval": "plan_approval_response"}[state.type]
            if response_type != expected:
                return
            if from_agent != state.target or to_agent != state.sender:
                return
            if state.status != "pending":
                return
            state.status = "approved" if approve else "rejected"

    def _format_team_events(self, msgs):
        lines = []
        for msg in msgs:
            metadata = msg.get("metadata", {})
            request_id = metadata.get("request_id")
            suffix = f" request_id={request_id}" if request_id else ""
            lines.append(f"[{msg['type']}{suffix}] {msg['from']}: {msg['content']}")
        return "[Team events]\n" + "\n".join(lines)
