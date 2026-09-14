"""TeammateRuntime:单队友 WORK/IDLE 循环 + 队友工具 + 收件箱处理。"""

import json

from ..core.hooks import POST_TOOL_USE, PRE_TOOL_USE
from ..tools import bash as bash_mod
from ..tools import files as files_mod
from ..tools import glob as glob_mod
from ..tools.registry import Tool, ToolRegistry

IDLE_SCAN_INTERVAL = 2.0


def _parse_args(arguments: str) -> dict:
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class TeammateRuntime:
    def __init__(self, *, name, role, prompt, task_id, require_plan,
                 provider, config, hooks, store, team):
        self.name = name
        self.provider = provider
        self.config = config
        self.hooks = hooks
        self.store = store
        self.team = team
        self.system = (
            f"You are '{name}', a {role}. Use tools to complete the assigned "
            "Task, then call complete_task and report a concise result. "
            "If the first user message contains [Assigned task], that Task is "
            "already claimed; do not call claim_task for it again. "
            "When asked for a plan, call submit_plan and wait for approval "
            "before bash or file changes. File and shell tools use the Task's "
            "working directory; that directory is not a sandbox. The runtime "
            "delivers your final text to Lead. Use send_message only for "
            "intermediate coordination, and address the coordinator as 'lead'."
        )
        self.messages = [{"role": "user", "content": prompt}]
        if task_id:
            task = store.load(task_id)
            cwd = team.assignment_cwd(name)
            self.messages[0]["content"] += (
                f"\n\n[Assigned task {task.id}] {task.subject}\n"
                f"{task.description}\nWork directory: {cwd}"
            )
        if require_plan:
            self.messages[0]["content"] += (
                "\n\n[Plan required] Submit a plan and wait for Lead approval "
                "before changing files or using bash."
            )
        self.tools = self._build_tools()

    def _build_tools(self) -> ToolRegistry:
        registry = ToolRegistry()
        timeout = self.config.bash_timeout
        max_output = self.config.max_output_chars
        registry.register(Tool(
            name="bash",
            description="Run a shell command in the task's working directory.",
            parameters={"type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"]},
            handler=lambda command: self._run_bash(command, timeout, max_output),
        ))
        registry.register(Tool(
            name="read_file",
            description="Read a file with line numbers in the task's working directory.",
            parameters={"type": "object",
                        "properties": {"path": {"type": "string"},
                                       "offset": {"type": "integer"},
                                       "limit": {"type": "integer"}},
                        "required": ["path"]},
            handler=lambda path, offset=1, limit=None: self._run_read(path, offset, limit),
        ))
        registry.register(Tool(
            name="write_file",
            description="Write content to a file in the task's working directory.",
            parameters={"type": "object",
                        "properties": {"path": {"type": "string"},
                                       "content": {"type": "string"}},
                        "required": ["path", "content"]},
            handler=lambda path, content: self._run_write(path, content),
        ))
        registry.register(Tool(
            name="edit_file",
            description="Replace old_text with new_text in the task's working directory.",
            parameters={"type": "object",
                        "properties": {"path": {"type": "string"},
                                       "old_text": {"type": "string"},
                                       "new_text": {"type": "string"}},
                        "required": ["path", "old_text", "new_text"]},
            handler=lambda path, old_text, new_text: self._run_edit(path, old_text, new_text),
        ))
        registry.register(Tool(
            name="glob",
            description="Find files matching a glob pattern in the task's working directory.",
            parameters={"type": "object",
                        "properties": {"pattern": {"type": "string"}},
                        "required": ["pattern"]},
            handler=lambda pattern: self._run_glob(pattern),
        ))
        registry.register(Tool(
            name="send_message",
            description="Send an intermediate message to 'lead' or an active teammate.",
            parameters={"type": "object",
                        "properties": {"to": {"type": "string"},
                                       "content": {"type": "string"}},
                        "required": ["to", "content"]},
            handler=lambda to, content: self.team.send_message(self.name, to, content),
        ))
        registry.register(Tool(
            name="submit_plan",
            description="Submit a work plan for Lead approval.",
            parameters={"type": "object",
                        "properties": {"plan": {"type": "string"}},
                        "required": ["plan"]},
            handler=lambda plan: self.team.submit_plan(self.name, plan),
        ))
        registry.register(Tool(
            name="list_tasks",
            description="List shared tasks.",
            parameters={"type": "object", "properties": {}},
            handler=lambda: self._render_tasks(),
        ))
        registry.register(Tool(
            name="claim_task",
            description="Claim a ready task.",
            parameters={"type": "object",
                        "properties": {"task_id": {"type": "string"}},
                        "required": ["task_id"]},
            handler=lambda task_id: self.team.claim_task(self.name, task_id),
        ))
        registry.register(Tool(
            name="complete_task",
            description="Complete an owned task.",
            parameters={"type": "object",
                        "properties": {"task_id": {"type": "string"}},
                        "required": ["task_id"]},
            handler=lambda task_id: self.team.complete_task(self.name, task_id),
        ))
        return registry

    def _current_cwd(self):
        try:
            return self.team.assignment_cwd(self.name), None
        except (FileNotFoundError, ValueError) as exc:
            return None, f"Error: Invalid task assignment: {exc}"

    def _run_bash(self, command, timeout, max_output):
        cwd, error = self._current_cwd()
        return error or bash_mod.run_bash(command, cwd, timeout, max_output)

    def _run_read(self, path, offset, limit):
        cwd, error = self._current_cwd()
        return error or files_mod.read_file(path, cwd, offset, limit)

    def _run_write(self, path, content):
        cwd, error = self._current_cwd()
        return error or files_mod.write_file(path, content, cwd)

    def _run_edit(self, path, old_text, new_text):
        cwd, error = self._current_cwd()
        return error or files_mod.edit_file(path, old_text, new_text, cwd)

    def _run_glob(self, pattern):
        cwd, error = self._current_cwd()
        return error or glob_mod.glob_files(pattern, cwd)

    def _render_tasks(self):
        tasks = self.team.list_tasks()
        if not tasks:
            return "No tasks."
        icon = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}
        lines = []
        for t in tasks:
            deps = f" (blocked_by: {', '.join(t.blocked_by)})" if t.blocked_by else ""
            owner = f" [{t.owner}]" if t.owner else ""
            wt = f" (worktree: {t.worktree})" if t.worktree else ""
            lines.append(f"{icon.get(t.status, '[?]')} {t.id}: {t.subject} "
                         f"[{t.status}]{owner}{deps}{wt}")
        return "\n".join(lines)

    def _run_tool(self, event):
        name = event["name"]
        gate = self.team.get_plan_gate(self.name)
        if (name in {"bash", "write_file", "edit_file"}
                and gate not in {"not_required", "approved"}):
            return f"Blocked: plan status is {gate}."
        blocked = self.hooks.first_block(PRE_TOOL_USE, event)
        if blocked is not None:
            return blocked
        result = self.tools.dispatch(name, json.dumps(event["input"]))
        self.hooks.trigger(POST_TOOL_USE, event, result)
        return result

    def handle_inbox(self, inbox):
        work_messages = []
        for msg in inbox:
            msg_type = msg.get("type", "message")
            if msg_type == "shutdown_request":
                accepted, notice = self.team.apply_shutdown_request(self.name, msg)
                if not accepted:
                    work_messages.append(notice)
                    continue
                self.team.send_message(
                    self.name, "lead", "Shutdown acknowledged.",
                    "shutdown_response", {"request_id": notice, "approve": True})
                return True
            if msg_type == "plan_approval_response":
                _, notice = self.team.apply_plan_response(self.name, msg)
                work_messages.append(notice)
                continue
            if msg_type == "plan_request":
                work_messages.append(f"[Plan required] {msg['content']}")
                continue
            work_messages.append(f"[Message from {msg['from']}] {msg['content']}")
        if work_messages:
            self.messages.append({"role": "user", "content": "\n".join(work_messages)})
        return False

    def wait_for_work(self):
        while True:
            inbox = self.team.wait_for_messages(self.name, IDLE_SCAN_INTERVAL)
            if inbox:
                before = len(self.messages)
                if self.handle_inbox(inbox):
                    return False
                if len(self.messages) > before:
                    return True
                continue
            task = self.team.claim_next_task(self.name)
            if not task:
                continue
            cwd = self.team.assignment_cwd(self.name)
            self.messages.append({"role": "user", "content": (
                f"[Auto-claimed task {task.id}] {task.subject}\n"
                f"{task.description}\nWork directory: {cwd}")})
            return True

    def work(self):
        if self.handle_inbox(self.team.read_inbox(self.name)):
            return "stop"
        self.team.set_active(self.name, "working")
        try:
            assistant = self.provider.chat(self.messages, self.tools.schemas())
        except Exception as exc:  # noqa: BLE001 - 队友对话失败转为错误消息,不中断线程
            self.team.send_message(self.name, "lead", f"{type(exc).__name__}: {exc}", "error")
            return "stop"
        self.messages.append(assistant)
        tool_calls = assistant.get("tool_calls") or []
        if tool_calls:
            for call in tool_calls:
                name = call["function"]["name"]
                arguments = call["function"].get("arguments") or "{}"
                call_id = call.get("id", "")
                event = {"name": name, "input": _parse_args(arguments), "id": call_id}
                result = self._run_tool(event)
                self.messages.append({"role": "tool", "tool_call_id": call_id,
                                      "content": result})
            return "continue"
        summary = assistant.get("content") or ""
        gate = self.team.get_plan_gate(self.name)
        if gate != "pending" and summary:
            self.team.send_message(self.name, "lead", summary, "result")
        if gate == "pending":
            self.team.set_active(self.name, "waiting_approval")
        else:
            self.team.release_completed(self.name)
            self.team.set_active(self.name, "idle")
            self.team.send_message(self.name, "lead", "Waiting for more work.",
                                   "idle_notification")
        return "idle"

    def run(self):
        try:
            state = "continue"
            while state != "stop":
                if state == "idle" and not self.wait_for_work():
                    break
                state = self.work()
        except Exception as exc:  # noqa: BLE001 - 队友主循环异常转为错误消息
            try:
                self.team.send_message(self.name, "lead", f"{type(exc).__name__}: {exc}", "error")
            except Exception:  # noqa: BLE001, S110 - 清理失败不应让队友线程崩溃
                pass
        finally:
            try:
                self.team.finish_teammate(self.name)
            except Exception:  # noqa: BLE001, S110 - 清理失败不应让队友线程崩溃
                pass
