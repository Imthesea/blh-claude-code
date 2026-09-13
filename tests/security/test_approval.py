from blh.security.approval import make_permission_hook
from blh.security.rules import PermissionRule


def make_hook(rules, answers=None):
    asked = []
    answers = iter(answers or [])

    def ask_fn(prompt):
        asked.append(prompt)
        return next(answers, "n")

    return make_permission_hook(rules, "/wd", ask_fn=ask_fn), asked


def test_allow_returns_none():
    hook, asked = make_hook([PermissionRule("*", "*", "allow")])
    assert hook({"name": "bash", "input": {"command": "ls"}}) is None
    assert asked == []


def test_deny_returns_reason():
    hook, _ = make_hook([PermissionRule("bash", "rm *", "deny")])
    result = hook({"name": "bash", "input": {"command": "rm -rf x"}})
    assert "denied by permission rule" in result


def test_ask_user_approves():
    hook, _ = make_hook([PermissionRule("bash", "*", "ask")], answers=["y"])
    assert hook({"name": "bash", "input": {"command": "make"}}) is None


def test_ask_user_rejects():
    hook, _ = make_hook([PermissionRule("bash", "*", "ask")], answers=["n"])
    assert hook({"name": "bash", "input": {"command": "make"}}) == "denied by user"


def test_file_tools_use_path_as_target():
    hook, asked = make_hook([PermissionRule("*", "*", "ask")], answers=["y"])
    hook({"name": "write_file", "input": {"path": "a.txt", "content": "x"}})
    assert "a.txt" in asked[0]


def test_ask_fn_eof_denies():
    def ask_fn(prompt):
        raise EOFError

    hook = make_permission_hook([PermissionRule("bash", "*", "ask")], "/wd", ask_fn=ask_fn)
    assert hook({"name": "bash", "input": {"command": "make"}}) == "denied by user"
