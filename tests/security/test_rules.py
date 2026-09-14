from blh.security.rules import DEFAULT_RULES, PermissionRule, match_rule


def test_first_matching_rule_wins():
    rules = [PermissionRule("bash", "git *", "allow"),
             PermissionRule("bash", "*", "ask")]
    assert match_rule(rules, "bash", "git status") == "allow"
    assert match_rule(rules, "bash", "make build") == "ask"


def test_tool_field_filters():
    rules = [PermissionRule("write_file", "*", "deny")]
    assert match_rule(rules, "bash", "ls") == "ask"  # 无匹配规则时默认 ask


def test_wildcard_tool_matches_any():
    rules = [PermissionRule("*", "*", "allow")]
    assert match_rule(rules, "read_file", "x.py") == "allow"


def test_default_rules_deny_force_push():
    assert match_rule(DEFAULT_RULES, "bash", "git push --force origin main") == "deny"
    assert match_rule(DEFAULT_RULES, "bash", "ls -la") == "ask"
    assert match_rule(DEFAULT_RULES, "read_file", "a.py") == "allow"


def test_mcp_tools_ask_by_default():
    assert match_rule(DEFAULT_RULES, "mcp__docs__search", "") == "ask"
    assert match_rule(DEFAULT_RULES, "connect_mcp", "") == "ask"
