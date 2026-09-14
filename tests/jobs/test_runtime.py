import time
from datetime import UTC, datetime

from blh.jobs.background import BackgroundManager
from blh.jobs.cron import CronScheduler
from blh.jobs.runtime import JobsRuntime


def make_runtime(tmp_path):
    return JobsRuntime(
        BackgroundManager(str(tmp_path)),
        CronScheduler(tmp_path / ".scheduled_tasks.json"),
    )


def test_consume_and_inject_cron_appends_scheduled_messages(tmp_path):
    runtime = make_runtime(tmp_path)
    job = runtime.cron.schedule("* * * * *", "run tests")
    runtime.cron.poll_due(datetime(2026, 9, 14, 10, 30, tzinfo=UTC))
    messages = [{"role": "user", "content": "hi"}]
    fired = runtime.consume_and_inject_cron(messages)
    assert [j.id for j in fired] == [job.id]
    assert messages[-1] == {"role": "user", "content": "[Scheduled] run tests"}


def test_start_background_returns_placeholder(tmp_path):
    runtime = make_runtime(tmp_path)
    result = runtime.start_background("echo hi")
    assert result.startswith("[Background task bg_")
    assert "later turn" in result


def test_inject_background_results_appends_notification(tmp_path):
    runtime = make_runtime(tmp_path)
    task_id = runtime.background.start("echo hello")
    deadline = time.monotonic() + 5
    while (runtime.background.tasks.get(task_id, {}).get("status") == "running"
           and time.monotonic() < deadline):
        time.sleep(0.01)
    messages = []
    assert runtime.inject_background_results(messages) == 1
    assert "<task_notification>" in messages[-1]["content"]


def test_inject_background_results_empty(tmp_path):
    runtime = make_runtime(tmp_path)
    messages = [{"role": "user", "content": "hi"}]
    assert runtime.inject_background_results(messages) == 0
    assert len(messages) == 1


def test_start_stop_idempotent(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.start()
    runtime.start()  # 幂等
    assert runtime._started
    runtime.stop()
    runtime.stop()  # 幂等
    assert not runtime._started
