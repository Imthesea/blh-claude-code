from blh.cli.repl import repl
from blh.core.config import Config
from blh.core.harness import Harness
from blh.core.hooks import HookBus
from blh.tools.registry import ToolRegistry


class MockProvider:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        return {"role": "assistant",
                "content": f"reply-{self.calls}",
                "tool_calls": None}


def make_harness():
    cfg = Config(api_key="k", base_url=None, model="m", workdir=".")
    return Harness(cfg, MockProvider(), ToolRegistry(), HookBus())


def test_repl_runs_turns_until_exit(monkeypatch, capsys):
    inputs = iter(["hello", "", "again", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    repl(make_harness())

    out = capsys.readouterr().out
    assert "reply-1" in out
    assert "reply-2" in out


def test_repl_eof_exits_cleanly(monkeypatch, capsys):
    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    repl(make_harness())  # 不抛异常即通过


def test_repl_starts_and_stops_runtime(tmp_path, monkeypatch, capsys):
    from blh.jobs.background import BackgroundManager
    from blh.jobs.cron import CronScheduler
    from blh.jobs.runtime import JobsRuntime
    cfg = Config(api_key="k", base_url=None, model="m", workdir=".")
    harness = Harness(
        cfg, MockProvider(), ToolRegistry(), HookBus(),
        jobs=JobsRuntime(BackgroundManager(str(tmp_path)),
                         CronScheduler(tmp_path / ".scheduled_tasks.json")))
    inputs = iter(["hello", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    repl(harness)
    assert not harness.jobs._started


def test_repl_starts_and_stops_team_runtime(tmp_path, monkeypatch, capsys):
    from blh.agents.bus import MessageBus
    from blh.agents.team import TeamRuntime
    from blh.jobs.background import BackgroundManager
    from blh.jobs.cron import CronScheduler
    from blh.jobs.runtime import JobsRuntime
    from blh.planning.tasks import TaskStore
    cfg = Config(api_key="k", base_url=None, model="m", workdir=".")
    jobs = JobsRuntime(BackgroundManager(str(tmp_path)),
                       CronScheduler(tmp_path / ".scheduled_tasks.json"))
    agents = TeamRuntime(
        store=TaskStore(tmp_path / ".tasks"),
        bus=MessageBus(tmp_path / ".mailboxes"),
        agent_lock=jobs.agent_lock,
        workdir=".",
        worktrees_dir=tmp_path / ".worktrees",
        provider=MockProvider(),
        config=cfg,
        hooks=HookBus(),
    )
    harness = Harness(cfg, MockProvider(), ToolRegistry(), HookBus(),
                      jobs=jobs, agents=agents)
    inputs = iter(["hello", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    repl(harness)
    assert not harness.agents._started
    assert not harness.jobs._started
