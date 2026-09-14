from datetime import UTC, datetime

import pytest

from blh.jobs.cron import CronScheduler, cron_matches, validate_cron


def _dt(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_cron_matches_every_minute():
    moment = _dt(2026, 9, 14, 10, 30)
    assert cron_matches("* * * * *", moment)
    assert cron_matches("*/5 * * * *", moment)
    assert not cron_matches("*/7 * * * *", moment)


def test_cron_matches_specific_minute_hour():
    assert cron_matches("30 10 * * *", _dt(2026, 9, 14, 10, 30))
    assert not cron_matches("30 10 * * *", _dt(2026, 9, 14, 10, 31))


def test_cron_matches_ranges_and_lists():
    assert cron_matches("0-30 10 * * *", _dt(2026, 9, 14, 10, 15))
    assert cron_matches("0,15,30 10 * * *", _dt(2026, 9, 14, 10, 15))
    assert not cron_matches("0,15,30 10 * * *", _dt(2026, 9, 14, 10, 20))


def test_cron_matches_weekday():
    monday = _dt(2026, 8, 10, 9, 0)  # 周一,cron 周一=1
    assert cron_matches("0 9 * * 1", monday)
    assert not cron_matches("0 9 * * 2", monday)


def test_validate_cron_accepts_valid():
    assert validate_cron("0 9 * * *") is None
    assert validate_cron("*/5 * * * *") is None
    assert validate_cron("0 9 * * 1-5") is None


def test_validate_cron_rejects_wrong_field_count():
    assert "Expected 5 fields" in validate_cron("0 9 * *")
    assert "Expected 5 fields" in validate_cron("0 9 * * * *")


def test_validate_cron_rejects_out_of_range():
    assert validate_cron("60 9 * * *") is not None
    assert "hour" in validate_cron("0 24 * * *")
    assert validate_cron("0 9 0 * *") is not None
    assert validate_cron("0 9 * 13 *") is not None


def test_validate_cron_rejects_bad_field():
    assert validate_cron("x 9 * * *") is not None
    assert validate_cron("*/0 * * * *") is not None
    assert validate_cron("5-1 * * * *") is not None


def make_scheduler(tmp_path):
    return CronScheduler(tmp_path / ".scheduled_tasks.json")


def test_schedule_returns_job(tmp_path):
    job = make_scheduler(tmp_path).schedule("0 9 * * *", "run tests")
    assert job.id.startswith("cron_")
    assert job.prompt == "run tests"
    assert job.recurring is True
    assert job.durable is True


def test_schedule_rejects_invalid_cron(tmp_path):
    with pytest.raises(ValueError):
        make_scheduler(tmp_path).schedule("bad cron", "x")


def test_schedule_rejects_empty_prompt(tmp_path):
    with pytest.raises(ValueError):
        make_scheduler(tmp_path).schedule("0 9 * * *", "  ")


def test_durable_schedule_persists_and_loads(tmp_path):
    path = tmp_path / ".scheduled_tasks.json"
    job = make_scheduler(tmp_path).schedule("0 9 * * *", "run tests")
    assert path.is_file()
    reloaded = CronScheduler(path)
    reloaded.load()
    assert [j.id for j in reloaded.list_jobs()] == [job.id]


def test_non_durable_schedule_not_persisted(tmp_path):
    path = tmp_path / ".scheduled_tasks.json"
    make_scheduler(tmp_path).schedule("0 9 * * *", "run tests", durable=False)
    assert not path.is_file()


def test_cancel_existing_and_missing(tmp_path):
    sched = make_scheduler(tmp_path)
    job = sched.schedule("0 9 * * *", "x")
    assert sched.cancel(job.id) == f"Cancelled {job.id}"
    assert sched.cancel(job.id) == f"Job {job.id} not found"


def test_poll_due_enqueues_once_per_minute(tmp_path):
    sched = make_scheduler(tmp_path)
    sched.schedule("* * * * *", "ping")
    moment = _dt(2026, 9, 14, 10, 30)
    sched.poll_due(moment)
    assert sched.has_queue()
    sched.poll_due(moment)  # last_fired 防同一分钟重复入队
    assert len(sched.consume_queue()) == 1


def test_consume_and_acknowledge_one_shot(tmp_path):
    sched = make_scheduler(tmp_path)
    job = sched.schedule("* * * * *", "ping", recurring=False)
    sched.poll_due(_dt(2026, 9, 14, 10, 30))
    fired = sched.consume_queue()
    assert [j.id for j in fired] == [job.id]
    sched.acknowledge(fired)
    assert sched.list_jobs() == []


def test_restore_puts_jobs_back(tmp_path):
    sched = make_scheduler(tmp_path)
    job = sched.schedule("* * * * *", "ping")
    sched.poll_due(_dt(2026, 9, 14, 10, 30))
    fired = sched.consume_queue()
    sched.restore(fired)
    assert sched.has_queue()
    assert [j.id for j in sched.consume_queue()] == [job.id]


def test_load_corrupt_file_reports_error(tmp_path, capsys):
    path = tmp_path / ".scheduled_tasks.json"
    path.write_text("{broken")
    sched = make_scheduler(tmp_path)
    sched.load()
    assert "could not load" in capsys.readouterr().out
    assert sched.list_jobs() == []
