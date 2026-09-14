import json

from blh.planning.tasks import TaskStore
from blh.planning.todo import TodoManager
from blh.planning.tools import register_planning_tools
from blh.tools.registry import ToolRegistry


def make_registry(tmp_path):
    registry = ToolRegistry()
    register_planning_tools(registry, TodoManager(),
                            TaskStore(tmp_path / ".tasks"))
    return registry


def test_registers_all_planning_tools(tmp_path):
    names = [s["function"]["name"] for s in make_registry(tmp_path).schemas()]
    assert set(names) == {
        "todo_write", "create_task", "update_task", "list_tasks",
        "get_task", "claim_task", "complete_task",
    }


def test_todo_write_returns_rendered_list(tmp_path):
    registry = make_registry(tmp_path)
    result = registry.dispatch(
        "todo_write",
        json.dumps({"todos": [{"content": "a", "status": "pending"}]}))
    assert result == "[ ] a"


def test_create_and_list_task_roundtrip(tmp_path):
    registry = make_registry(tmp_path)
    created = registry.dispatch("create_task", json.dumps({"subject": "ship it"}))
    assert created.startswith("Created task_")
    assert "ship it" in registry.dispatch("list_tasks", "{}")


def test_get_task_returns_json(tmp_path):
    registry = make_registry(tmp_path)
    created = registry.dispatch("create_task", json.dumps({"subject": "x"}))
    task_id = created.split(":")[0].split(" ")[1]
    data = json.loads(registry.dispatch("get_task",
                                        json.dumps({"task_id": task_id})))
    assert data["id"] == task_id
    assert data["subject"] == "x"


def test_claim_complete_flow(tmp_path):
    registry = make_registry(tmp_path)
    created = registry.dispatch("create_task", json.dumps({"subject": "x"}))
    task_id = created.split(":")[0].split(" ")[1]
    assert registry.dispatch("claim_task",
                             json.dumps({"task_id": task_id})) == f"Claimed {task_id}."
    assert registry.dispatch("complete_task",
                             json.dumps({"task_id": task_id})) == f"Completed {task_id}."


def test_update_task_adds_dependency(tmp_path):
    registry = make_registry(tmp_path)
    a = registry.dispatch("create_task", json.dumps({"subject": "a"}))
    b = registry.dispatch("create_task", json.dumps({"subject": "b"}))
    id_a = a.split(":")[0].split(" ")[1]
    id_b = b.split(":")[0].split(" ")[1]
    result = registry.dispatch("update_task",
                               json.dumps({"task_id": id_b,
                                           "add_blocked_by": [id_a]}))
    assert f"blocked by {id_a}" in result
