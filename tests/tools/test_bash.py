import sys

from blh.tools.bash import run_bash


def test_run_bash_captures_output(tmp_path):
    out = run_bash("echo hello", str(tmp_path))
    assert "hello" in out


def test_run_bash_runs_in_workdir(tmp_path):
    marker = tmp_path / "marker.txt"
    marker.write_text("x")
    cmd = "dir marker.txt /b" if sys.platform == "win32" else "ls marker.txt"
    assert "marker.txt" in run_bash(cmd, str(tmp_path))


def test_run_bash_truncates_long_output(tmp_path):
    out = run_bash(f"{sys.executable} -c \"print('x' * 50000)\"", str(tmp_path), max_output=1000)
    assert len(out) < 1200
    assert "truncated" in out


def test_run_bash_timeout(tmp_path):
    cmd = f"{sys.executable} -c \"import time; time.sleep(10)\""
    assert "timed out" in run_bash(cmd, str(tmp_path), timeout=1)
