import json

from blh.jobs.cron import CronScheduler
from blh.jobs.tools import register_jobs_tools
from blh.tools.registry import ToolRegistry


def make_registry(tmp_path):
    registry = ToolRegistry()
    register_jobs_tools(registry, CronScheduler(tmp_path / ".scheduled_tasks.json"))
    return registry


def test_registers_cron_tools(tmp_path):
    names = [s["function"]["name"] for s in make_registry(tmp_path).schemas()]
    assert set(names) == {"schedule_cron", "list_crons", "cancel_cron"}


def test_schedule_cron_returns_scheduled(tmp_path):
    registry = make_registry(tmp_path)
    result = registry.dispatch(
        "schedule_cron", json.dumps({"cron": "0 9 * * *", "prompt": "run tests"}))
    assert result.startswith("Scheduled cron_")
    assert "run tests" in result


def test_list_crons_roundtrip(tmp_path):
    registry = make_registry(tmp_path)
    registry.dispatch(
        "schedule_cron", json.dumps({"cron": "0 9 * * *", "prompt": "run tests"}))
    assert "run tests" in registry.dispatch("list_crons", "{}")


def test_cancel_cron(tmp_path):
    registry = make_registry(tmp_path)
    scheduled = registry.dispatch(
        "schedule_cron", json.dumps({"cron": "0 9 * * *", "prompt": "x"}))
    job_id = scheduled.split(":")[0].split(" ")[1]
    assert registry.dispatch("cancel_cron",
                             json.dumps({"job_id": job_id})) == f"Cancelled {job_id}"


def test_schedule_cron_invalid_expr(tmp_path):
    registry = make_registry(tmp_path)
    result = registry.dispatch(
        "schedule_cron", json.dumps({"cron": "bad", "prompt": "x"}))
    assert result.startswith("error: tool 'schedule_cron' failed")
