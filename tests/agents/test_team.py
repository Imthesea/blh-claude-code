import threading

from blh.agents.bus import MessageBus
from blh.agents.team import TeamRuntime
from blh.core.config import Config
from blh.core.hooks import HookBus
from blh.planning.tasks import TaskStore


class MockProvider:
    def chat(self, messages, tools, max_tokens=None):
        return {"role": "assistant", "content": "done", "tool_calls": None}


def make_team(tmp_path):
    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    store = TaskStore(tmp_path / ".tasks")
    bus = MessageBus(tmp_path / ".mailboxes")
    return TeamRuntime(
        store=store, bus=bus, agent_lock=threading.Lock(),
        workdir=str(tmp_path), worktrees_dir=tmp_path / ".worktrees",
        provider=MockProvider(), config=cfg, hooks=HookBus())


def test_claim_task_assigns_cwd(tmp_path):
    team = make_team(tmp_path)
    task = team.store.create("ship")
    result = team.claim_task("alice", task.id)
    assert result == f"Claimed {task.id}."
    assert team.assignments["alice"]["task_id"] == task.id
    assert team.store.load(task.id).owner == "alice"


def test_claim_task_rejects_second_assignment(tmp_path):
    team = make_team(tmp_path)
    a = team.store.create("a")
    b = team.store.create("b")
    team.claim_task("alice", a.id)
    assert "complete its current task first" in team.claim_task("alice", b.id)


def test_claim_next_task_atomic(tmp_path):
    team = make_team(tmp_path)
    task = team.store.create("only")
    results = []

    def claim(name):
        claimed = team.claim_next_task(name)
        results.append(claimed.id if claimed else None)

    threads = [threading.Thread(target=claim, args=(n,)) for n in ("alice", "bob")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [task_id for task_id in results if task_id] == [task.id]


def test_consume_and_inject_team(tmp_path):
    team = make_team(tmp_path)
    team.bus.send("bob", "lead", "auth done", "result")
    messages = [{"role": "user", "content": "hi"}]
    assert team.consume_and_inject_team(messages) == 1
    assert messages[-1]["content"].startswith("[Team events]")
    assert "auth done" in messages[-1]["content"]


def test_request_shutdown_protocol(tmp_path):
    team = make_team(tmp_path)
    team.active_teammates["bob"] = "working"
    result = team.request_shutdown("bob")
    assert "Shutdown requested" in result
    assert any(s.type == "shutdown" for s in team.pending_requests.values())
    inbox = team.bus.read_inbox("bob")
    assert inbox[0]["type"] == "shutdown_request"


def test_review_plan_protocol(tmp_path):
    team = make_team(tmp_path)
    team.active_teammates["bob"] = "working"
    team.plan_gates["bob"] = "required"
    result = team.submit_plan("bob", "do auth first")
    assert "Plan submitted" in result
    request_id = next(iter(team.pending_requests))
    assert "Plan approved" in team.review_plan(request_id, True)
    assert team.pending_requests[request_id].status == "approved"
