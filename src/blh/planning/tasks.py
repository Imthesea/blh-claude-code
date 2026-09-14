"""持久化任务图:Task 数据类 + TaskStore(CRUD、依赖、状态机)。"""

import json
import re
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Task:
    id: str
    subject: str
    description: str
    status: str
    owner: str | None
    blocked_by: list[str]


VALID_STATUSES = ("pending", "in_progress", "completed")


class TaskStore:
    TASK_ID_PATTERN = re.compile(r"^task_[0-9a-f]{8}$")

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def _path(self, task_id: str) -> Path:
        if (not isinstance(task_id, str)
                or not self.TASK_ID_PATTERN.fullmatch(task_id)):
            raise ValueError(f"invalid task ID: {task_id!r}")
        return self.directory / f"{task_id}.json"

    def exists(self, task_id: str) -> bool:
        return self._path(task_id).is_file()

    def create(self, subject: str, description: str = "") -> Task:
        subject = subject.strip()
        if not subject:
            raise ValueError("task subject cannot be empty")
        self.directory.mkdir(parents=True, exist_ok=True)
        for _ in range(100):
            task = Task(
                id=f"task_{secrets.token_hex(4)}",
                subject=subject,
                description=description,
                status="pending",
                owner=None,
                blocked_by=[],
            )
            try:
                with self._path(task.id).open("x", encoding="utf-8") as f:
                    json.dump(asdict(task), f, indent=2)
                return task
            except FileExistsError:
                continue
        raise RuntimeError("could not allocate a unique task ID")

    def load(self, task_id: str) -> Task:
        data = json.loads(self._path(task_id).read_text(encoding="utf-8"))
        task = Task(**data)
        if task.id != task_id:
            raise ValueError(f"task file ID {task.id!r} != requested {task_id!r}")
        if task.status not in VALID_STATUSES:
            raise ValueError(f"invalid task status: {task.status!r}")
        return task

    def save(self, task: Task) -> None:
        self._path(task.id).write_text(
            json.dumps(asdict(task), indent=2), encoding="utf-8")

    def list(self) -> list[Task]:
        if not self.directory.exists():
            return []
        return [self.load(p.stem)
                for p in sorted(self.directory.glob("task_*.json"))]
