from blh.core.hooks import HookBus


def test_trigger_calls_in_registration_order():
    bus = HookBus()
    order = []
    bus.register("Stop", lambda: order.append("a"))
    bus.register("Stop", lambda: order.append("b"))
    bus.trigger("Stop")
    assert order == ["a", "b"]


def test_trigger_collects_results():
    bus = HookBus()
    bus.register("E", lambda x: x + 1)
    bus.register("E", lambda x: x + 2)
    assert bus.trigger("E", 0) == [1, 2]


def test_first_block_returns_first_non_none():
    bus = HookBus()
    bus.register("PreToolUse", lambda e: None)
    bus.register("PreToolUse", lambda e: "blocked")
    bus.register("PreToolUse", lambda e: "never reached")
    assert bus.first_block("PreToolUse", {}) == "blocked"


def test_first_block_none_when_no_hook():
    assert HookBus().first_block("PreToolUse", {}) is None


def test_first_block_none_when_all_hooks_pass():
    bus = HookBus()
    bus.register("PreToolUse", lambda e: None)
    bus.register("PreToolUse", lambda e: None)
    assert bus.first_block("PreToolUse", {}) is None
