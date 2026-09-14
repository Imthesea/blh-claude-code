import time

import pytest

from blh.jobs.background import BackgroundManager


def make_manager(tmp_path):
    return BackgroundManager(str(tmp_path))


def _wait_status(mgr, task_id, status, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with mgr._lock:
            current = mgr.tasks.get(task_id, {}).get("status")
        if current == status:
            return True
        time.sleep(0.01)
    return False


def test_start_returns_bg_id_and_tracks_running(tmp_path):
    mgr = make_manager(tmp_path)
    bg_id = mgr.start("echo hi")
    assert bg_id.startswith("bg_")
    with mgr._lock:
        assert mgr.tasks[bg_id]["status"] == "running"


def test_start_rejects_empty_command(tmp_path):
    with pytest.raises(ValueError):
        make_manager(tmp_path).start("   ")


def test_collect_returns_completed_notification(tmp_path):
    mgr = make_manager(tmp_path)
    bg_id = mgr.start("echo hello")
    assert _wait_status(mgr, bg_id, "completed")
    notifications = mgr.collect()
    assert len(notifications) == 1
    assert f"<task_id>{bg_id}</task_id>" in notifications[0]
    assert "<status>completed</status>" in notifications[0]
    assert "hello" in notifications[0]


def test_collect_empty_when_nothing_done(tmp_path):
    assert make_manager(tmp_path).collect() == []


def test_failed_command_marks_failed(tmp_path):
    mgr = make_manager(tmp_path)
    bg_id = mgr.start("exit 1")
    assert _wait_status(mgr, bg_id, "failed")
    notifications = mgr.collect()
    assert "<status>failed</status>" in notifications[0]


def test_collect_is_one_shot(tmp_path):
    mgr = make_manager(tmp_path)
    bg_id = mgr.start("echo once")
    assert _wait_status(mgr, bg_id, "completed")
    assert len(mgr.collect()) == 1
    assert mgr.collect() == []
