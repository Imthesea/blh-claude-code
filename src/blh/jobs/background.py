"""后台任务:慢 bash 命令放入 daemon 线程,后续轮次收集完成通知。"""

import subprocess
import threading


def _run_bash_process(command: str, workdir: str, timeout: int,
                      max_output: int) -> tuple[str, int | None]:
    try:
        proc = subprocess.run(
            command, shell=True, cwd=workdir, check=False,
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        if len(output) > max_output:
            output = (output[:max_output]
                      + f"\n... [truncated, {len(output)} chars total]")
        return output or "(no output)", proc.returncode
    except subprocess.TimeoutExpired:
        return f"error: command timed out after {timeout}s", None
    except OSError as error:
        return f"Error: {type(error).__name__}: {error}", None


class BackgroundManager:
    def __init__(self, workdir: str, timeout: int = 120, max_output: int = 30000):
        self.workdir = workdir
        self.timeout = timeout
        self.max_output = max_output
        self.tasks: dict[str, dict] = {}
        self.results: dict[str, str] = {}
        self._ready: list[str] = []
        self._counter = 0
        self._lock = threading.Lock()

    def start(self, command: str) -> str:
        command = str(command).strip()
        if not command:
            raise ValueError("Bash command cannot be empty")
        with self._lock:
            self._counter += 1
            task_id = f"bg_{self._counter:04d}"
            self.tasks[task_id] = {"command": command, "status": "running"}
        thread = threading.Thread(
            target=self._run, args=(task_id, command), daemon=True)
        thread.start()
        return task_id

    def _run(self, task_id: str, command: str) -> None:
        try:
            output, exit_code = _run_bash_process(
                command, self.workdir, self.timeout, self.max_output)
            status = "completed" if exit_code == 0 else "failed"
        except Exception as error:  # noqa: BLE001 - worker 崩溃也要记录为 failed
            output = f"Error: {type(error).__name__}: {error}"
            status = "failed"
        with self._lock:
            task = self.tasks.get(task_id)
            if task is None:
                return
            task["status"] = status
            self.results[task_id] = output
            self._ready.append(task_id)

    def collect(self) -> list[str]:
        with self._lock:
            ready = []
            for task_id in self._ready:
                task = self.tasks.pop(task_id, None)
                result = self.results.pop(task_id, "")
                if task is not None:
                    ready.append((task_id, task, result))
            self._ready.clear()
        notifications = []
        for task_id, task, result in ready:
            notifications.append(
                f"<task_notification>\n"
                f"  <task_id>{task_id}</task_id>\n"
                f"  <status>{task['status']}</status>\n"
                f"  <command>{task['command']}</command>\n"
                f"  <summary>{result[:500]}</summary>\n"
                f"</task_notification>")
        return notifications
