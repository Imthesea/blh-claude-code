from blh.tools.glob import glob_files


def test_glob_matches_relative(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("")
    out = glob_files("**/*.py", str(tmp_path))
    assert "a.py" in out
    assert "b.py" in out


def test_glob_no_matches(tmp_path):
    assert glob_files("*.rs", str(tmp_path)) == "(no matches)"
