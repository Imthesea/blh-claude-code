import json

from blh.cli.main import build_harness


def test_build_harness_wires_compactor_and_compact_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.compactor is not None
    assert harness.compactor.transcript_dir == tmp_path / ".transcripts"
    assert (harness.compactor.tool_results_dir
            == tmp_path / ".task_outputs" / "tool-results")
    names = [s["function"]["name"] for s in harness.tools.schemas()]
    assert "compact" in names


def test_build_harness_wires_planning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.todo_manager is not None
    names = [s["function"]["name"] for s in harness.tools.schemas()]
    for name in ("todo_write", "create_task", "update_task", "list_tasks",
                 "get_task", "claim_task", "complete_task"):
        assert name in names


def test_build_harness_wires_memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.memory is not None
    assert harness.memory.store.directory == tmp_path / ".memory"


def test_build_harness_wires_jobs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.jobs is not None
    names = [s["function"]["name"] for s in harness.tools.schemas()]
    for name in ("schedule_cron", "list_crons", "cancel_cron"):
        assert name in names


def test_build_harness_loads_persisted_cron(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    (tmp_path / ".scheduled_tasks.json").write_text(
        json.dumps([{"id": "cron_abc12345", "cron": "0 9 * * *",
                     "prompt": "run tests", "recurring": True, "durable": True,
                     "pending_delivery": False, "last_fired": None}]))
    harness = build_harness(workdir=str(tmp_path))
    assert [j.id for j in harness.jobs.cron.list_jobs()] == ["cron_abc12345"]


def test_build_harness_wires_agents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.agents is not None
    names = [s["function"]["name"] for s in harness.tools.schemas()]
    for name in ("task", "spawn_teammate", "list_teammates", "send_message",
                 "request_shutdown", "request_plan", "review_plan",
                 "create_worktree"):
        assert name in names


def test_build_harness_wires_extensions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.extensions is not None
    names = [s["function"]["name"] for s in harness.tools.schemas()]
    assert "load_skill" in names
    assert "connect_mcp" in names
