import json

from blh.agents.tools import register_agent_tools
from blh.tools.registry import ToolRegistry


class FakeSubagent:
    def __init__(self):
        self.calls = []

    def run(self, prompt):
        self.calls.append(prompt)
        return "sub-result"


class FakeTeam:
    def spawn_teammate(self, name, role, prompt, task_id=None, require_plan=False):
        return f"spawned {name}"

    def list_teammates(self):
        return "no teammates"

    def lead_send_message(self, to, content):
        return f"sent {to}"

    def request_shutdown(self, teammate):
        return f"shutdown {teammate}"

    def request_plan(self, teammate, task):
        return f"plan {teammate}"

    def review_plan(self, request_id, approve, feedback=""):
        return f"reviewed {request_id}"

    def create_worktree(self, name, task_id):
        return f"wt {name}"


def make_registry():
    registry = ToolRegistry()
    register_agent_tools(registry, FakeSubagent(), FakeTeam())
    return registry


def test_registers_agent_tools():
    names = {s["function"]["name"] for s in make_registry().schemas()}
    assert names == {"task", "spawn_teammate", "list_teammates", "send_message",
                     "request_shutdown", "request_plan", "review_plan",
                     "create_worktree"}


def test_task_dispatches_to_subagent():
    sub = FakeSubagent()
    registry = ToolRegistry()
    register_agent_tools(registry, sub, FakeTeam())
    result = registry.dispatch("task", json.dumps({"prompt": "explore"}))
    assert result == "sub-result"
    assert sub.calls == ["explore"]


def test_spawn_teammate_dispatches():
    registry = make_registry()
    result = registry.dispatch("spawn_teammate", json.dumps(
        {"name": "bob", "role": "worker", "prompt": "go"}))
    assert result == "spawned bob"
