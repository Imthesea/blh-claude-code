import json

from blh.core.config import Config
from blh.tools import register_builtin_tools
from blh.tools.registry import ToolRegistry


def make_registry(tmp_path):
    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    reg = ToolRegistry()
    register_builtin_tools(reg, cfg)
    return reg


def test_five_tools_registered(tmp_path):
    names = [s["function"]["name"] for s in make_registry(tmp_path).schemas()]
    assert sorted(names) == ["bash", "edit_file", "glob", "read_file", "write_file"]


def test_builtin_dispatch_roundtrip(tmp_path):
    reg = make_registry(tmp_path)
    out = reg.dispatch("write_file", json.dumps({"path": "x.txt", "content": "hello"}))
    assert "wrote" in out
    out = reg.dispatch("read_file", json.dumps({"path": "x.txt"}))
    assert "hello" in out


def test_bash_has_run_in_background_param(tmp_path):
    reg = make_registry(tmp_path)
    bash = next(s for s in reg.schemas() if s["function"]["name"] == "bash")
    assert "run_in_background" in bash["function"]["parameters"]["properties"]
