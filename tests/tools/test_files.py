import os
import subprocess

import pytest

from blh.tools.files import PathEscapeError, edit_file, read_file, safe_path, write_file


def test_safe_path_inside(tmp_path):
    p = safe_path("a/b.txt", str(tmp_path))
    assert str(p).startswith(str(tmp_path.resolve()))


def test_safe_path_escape_rejected(tmp_path):
    with pytest.raises(PathEscapeError):
        safe_path("../outside.txt", str(tmp_path))
    with pytest.raises(PathEscapeError):
        safe_path("C:/Windows/System32/drivers/etc/hosts", str(tmp_path))


def test_write_then_read(tmp_path):
    wd = str(tmp_path)
    write_file("notes.txt", "line1\nline2\nline3", wd)
    assert read_file("notes.txt", wd) == "1\tline1\n2\tline2\n3\tline3"


def test_read_offset_limit(tmp_path):
    wd = str(tmp_path)
    write_file("n.txt", "a\nb\nc\nd", wd)
    assert read_file("n.txt", wd, offset=2, limit=2) == "2\tb\n3\tc"


def test_edit_unique_replacement(tmp_path):
    wd = str(tmp_path)
    write_file("e.txt", "foo bar foo", wd)
    result = edit_file("e.txt", "bar", "baz", wd)
    assert "edited" in result
    assert read_file("e.txt", wd) == "1\tfoo baz foo"


def test_edit_non_unique_rejected(tmp_path):
    wd = str(tmp_path)
    write_file("e2.txt", "foo foo", wd)
    assert "2 times" in edit_file("e2.txt", "foo", "x", wd)


def test_safe_path_symlink_escape_rejected(tmp_path):
    outside = tmp_path.parent / "symlink-escape-target"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        # 某些 Windows 环境下 symlink 其实已创建成功却仍抛 WinError 2;
        # 确实不存在时,回退到等效的 directory junction(无需特权)
        if not os.path.lexists(link):
            if os.name != "nt":
                pytest.skip("cannot create symlink")
            r = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                capture_output=True,
                text=True,
                check=False,
            )
            if r.returncode != 0:
                pytest.skip(f"cannot create symlink or junction: {r.stdout}{r.stderr}")
    with pytest.raises(PathEscapeError):
        safe_path("link/escape.txt", str(tmp_path))


def test_safe_path_absolute_inside_allowed(tmp_path):
    p = safe_path(str(tmp_path / "inside.txt"), str(tmp_path))
    assert p == (tmp_path / "inside.txt").resolve()


def test_write_creates_parent_dirs(tmp_path):
    wd = str(tmp_path)
    write_file("a/b/c.txt", "x", wd)
    assert (tmp_path / "a" / "b" / "c.txt").read_text(encoding="utf-8") == "x"


def test_edit_non_utf8_raises(tmp_path):
    wd = str(tmp_path)
    (tmp_path / "gbk.txt").write_bytes("中文".encode("gbk"))
    with pytest.raises(UnicodeDecodeError):
        edit_file("gbk.txt", "中文", "x", wd)


def test_edit_empty_old_text_rejected(tmp_path):
    wd = str(tmp_path)
    write_file("e3.txt", "foo", wd)
    assert "must not be empty" in edit_file("e3.txt", "", "x", wd)
