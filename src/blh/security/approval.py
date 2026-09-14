import threading
from collections.abc import Callable

from .rules import PermissionRule, match_rule


def make_permission_hook(rules: list[PermissionRule], workdir: str,
                         ask_fn: Callable[[str], str] = input) -> Callable[[dict], str | None]:
    """生成 PreToolUse hook:返回 None 放行,返回字符串则作为拒绝原因。"""

    def permission_hook(event: dict) -> str | None:
        tool = event["name"]
        args = event["input"]
        target = args.get("command") or args.get("path") or ""
        action = match_rule(rules, tool, target)
        if action == "allow":
            return None
        if action == "deny":
            return f"denied by permission rule ({tool}: {target})"
        if threading.current_thread() is not threading.main_thread():
            return "denied: cannot request approval from a scheduled turn"
        try:
            answer = ask_fn(f"allow {tool}({target})? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            return "denied by user"
        if answer.strip().lower() in ("y", "yes"):
            return None
        return "denied by user"

    return permission_hook
