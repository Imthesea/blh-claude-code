import fnmatch
from dataclasses import dataclass


@dataclass
class PermissionRule:
    tool: str      # 工具名或 "*"
    pattern: str   # 目标 fnmatch 模式(bash 命令 / 文件路径)
    action: str    # "allow" | "ask" | "deny"


DEFAULT_RULES = [
    PermissionRule("bash", "git push --force*", "deny"),
    PermissionRule("bash", "rm -rf /*", "deny"),
    PermissionRule("bash", "*", "ask"),
    PermissionRule("*", "*", "allow"),
]


def match_rule(rules: list[PermissionRule], tool: str, target: str) -> str:
    for rule in rules:
        if rule.tool not in (tool, "*"):
            continue
        if fnmatch.fnmatch(target, rule.pattern):
            return rule.action
    return "ask"
