"""planning 工具注册:把 TodoManager/TaskStore 封装为模型工具。"""

import json
from dataclasses import asdict

from ..tools.registry import Tool, ToolRegistry
from .tasks import TaskStore
from .todo import TodoManager

_MARKS = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]"}


def _created(task) -> str:
    return f"Created {task.id}: {task.subject}"


def _updated(task) -> str:
    if task.blocked_by:
        return f"Updated {task.id} (blocked by {', '.join(task.blocked_by)})."
    return f"Updated {task.id}."


def _listed(tasks) -> str:
    if not tasks:
        return "No tasks."
    lines = []
    for task in tasks:
        suffix = (f" (blocked by: {', '.join(task.blocked_by)})"
                  if task.blocked_by else "")
        lines.append(f"{_MARKS[task.status]} {task.id}: {task.subject}{suffix}")
    return "\n".join(lines)


def register_planning_tools(registry: ToolRegistry,
                            todo_manager: TodoManager,
                            task_store: TaskStore) -> None:
    registry.register(Tool(
        name="todo_write",
        description="Create or replace the todo list to plan and track progress.",
        parameters={"type": "object", "properties": {
            "todos": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "status": {"type": "string",
                               "enum": ["pending", "in_progress",
                                        "completed"]},
                },
                "required": ["content"],
            }},
        }, "required": ["todos"]},
        handler=lambda todos: todo_manager.update(todos),
    ))
    registry.register(Tool(
        name="create_task",
        description="Create a durable task, recoverable across sessions.",
        parameters={"type": "object", "properties": {
            "subject": {"type": "string"},
            "description": {"type": "string"},
        }, "required": ["subject"]},
        handler=lambda subject, description="": _created(
            task_store.create(subject, description)),
    ))
    registry.register(Tool(
        name="update_task",
        description="Add dependency edges to an existing task by ID.",
        parameters={"type": "object", "properties": {
            "task_id": {"type": "string"},
            "add_blocked_by": {"type": "array",
                               "items": {"type": "string"}},
        }, "required": ["task_id", "add_blocked_by"]},
        handler=lambda task_id, add_blocked_by: _updated(
            task_store.update_dependencies(task_id, add_blocked_by)),
    ))
    registry.register(Tool(
        name="list_tasks",
        description="List all tasks, one line each.",
        parameters={"type": "object", "properties": {}},
        handler=lambda: _listed(task_store.list()),
    ))
    registry.register(Tool(
        name="get_task",
        description="Show the full JSON of one task by ID.",
        parameters={"type": "object", "properties": {
            "task_id": {"type": "string"}}, "required": ["task_id"]},
        handler=lambda task_id: json.dumps(
            asdict(task_store.load(task_id)), indent=2),
    ))
    registry.register(Tool(
        name="claim_task",
        description="Claim an unblocked pending task (pending -> in_progress).",
        parameters={"type": "object", "properties": {
            "task_id": {"type": "string"}}, "required": ["task_id"]},
        handler=lambda task_id: task_store.claim(task_id),
    ))
    registry.register(Tool(
        name="complete_task",
        description="Complete an in_progress task (in_progress -> completed).",
        parameters={"type": "object", "properties": {
            "task_id": {"type": "string"}}, "required": ["task_id"]},
        handler=lambda task_id: task_store.complete(task_id),
    ))
