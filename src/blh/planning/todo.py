"""进程内 todo 清单:校验、渲染、连续未更新提醒计数。"""

VALID_STATUSES = ("pending", "in_progress", "completed")
MAX_ITEMS = 20


class TodoManager:
    def __init__(self):
        self.items: list[dict] = []
        self.rounds_since_todo = 0

    def update(self, todos: list) -> str:
        if not isinstance(todos, list):
            raise TypeError("todos must be a list")
        items = []
        for todo in todos:
            if not isinstance(todo, dict):
                raise TypeError("each todo must be an object")
            content = str(todo.get("content", "")).strip()
            if not content:
                raise ValueError("todo content cannot be empty")
            status = todo.get("status", "pending")
            if status not in VALID_STATUSES:
                raise ValueError(
                    f"invalid status {status!r}; must be one of {VALID_STATUSES}")
            items.append({"content": content, "status": status})
        if len(items) > MAX_ITEMS:
            raise ValueError(f"too many todos: {len(items)} (max {MAX_ITEMS})")
        self.items = items
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."
        marks = {"pending": "[ ]", "in_progress": "[~]",
                 "completed": "[x]"}
        return "\n".join(
            f"{marks[todo['status']]} {todo['content']}" for todo in self.items)

    def note_round(self, used_todo: bool) -> str | None:
        self.rounds_since_todo = 0 if used_todo else self.rounds_since_todo + 1
        if self.rounds_since_todo >= 3:
            self.rounds_since_todo = 0
            return "<reminder>Update your todos.</reminder>"
        return None
