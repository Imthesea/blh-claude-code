import json

from blh.agents.teammate import TeammateRuntime
from blh.core.config import Config
from blh.core.hooks import HookBus
from blh.planning.tasks import TaskStore


class MockProvider:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def chat(self, messages, tools, max_tokens=None):
        self.calls += 1
        if not self.scripted:
            raise AssertionError("MockProvider exhausted")
        return self.scripted.pop(0)


def tool_call_msg(call_id, name, args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def text_msg(text):
    return {"role": "assistant", "content": text, "tool_calls": None}


class FakeTeam:
    def __init__(self):
        self.sent = []
        self.gate = "not_required"
        self.cwd = "/fake"

    def assignment_cwd(self, owner):
        return self.cwd

    def claim_task(self, owner, task_id):
        return f"Claimed {task_id}."

    def complete_task(self, owner, task_id):
        return f"Completed {task_id}."

    def list_tasks(self):
        return []

    def send_message(self, from_name, to, content, msg_type="message", metadata=None):
        self.sent.append((from_name, to, content, msg_type))
        return f"Sent to {to}"

    def submit_plan(self, from_name, plan):
        return "Plan submitted (req_000001)."

    def apply_shutdown_request(self, name, msg):
        return True, "req_000001"

    def apply_plan_response(self, name, msg):
        return True, "[Plan approved] ok"

    def get_plan_gate(self, name):
        return self.gate

    def set_active(self, name, status):
        pass

    def release_completed(self, name):
        pass

    def finish_teammate(self, name):
        pass

    def claim_next_task(self, name):
        return None

    def read_inbox(self, name):
        return []

    def wait_for_messages(self, name, timeout=None):
        return []


def make_teammate(tmp_path, team, scripted):
    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    store = TaskStore(tmp_path / ".tasks")
    return TeammateRuntime(name="bob", role="worker", prompt="do it",
                           task_id=None, require_plan=False,
                           provider=MockProvider(scripted), config=cfg,
                           hooks=HookBus(), store=store, team=team)


def test_work_returns_idle_and_sends_result(tmp_path):
    team = FakeTeam()
    rt = make_teammate(tmp_path, team, [text_msg("all done")])
    assert rt.work() == "idle"
    types = [m[3] for m in team.sent]
    assert "result" in types
    assert "idle_notification" in types


def test_workspace_tools_require_task(tmp_path):
    class NoTaskTeam(FakeTeam):
        def assignment_cwd(self, owner):
            raise ValueError("Claim a Task before using workspace tools.")

    rt = make_teammate(tmp_path, NoTaskTeam(), [])
    assert "Claim a Task" in rt._run_write("x.txt", "y")


def test_handle_inbox_shutdown(tmp_path):
    team = FakeTeam()
    rt = make_teammate(tmp_path, team, [])
    msg = {"from": "lead", "to": "bob", "content": "stop",
           "type": "shutdown_request", "metadata": {"request_id": "req_000001"}}
    assert rt.handle_inbox([msg]) is True
    assert any(m[3] == "shutdown_response" for m in team.sent)


def test_plan_gate_blocks_write(tmp_path):
    team = FakeTeam()
    team.gate = "required"
    rt = make_teammate(tmp_path, team, [
        tool_call_msg("c1", "write_file", {"path": "x.txt", "content": "y"}),
        text_msg("done"),
    ])
    assert rt.work() == "continue"
    assert not (tmp_path / "x.txt").exists()
