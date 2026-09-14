import pytest

from blh.goals.evaluator import PromptGoalEvaluator
from blh.goals.types import GoalError


class _FakeProvider:
    def __init__(self, text):
        self._text = text
        self.calls = []

    def chat(self, messages, tools, max_tokens=None):
        self.calls.append((messages, tools, max_tokens))
        return {"role": "assistant", "content": self._text}


def test_evaluate_ok():
    provider = _FakeProvider('{"ok": true, "reason": "done", "impossible": false}')
    result = PromptGoalEvaluator(provider).evaluate(
        "x", [{"role": "user", "content": "hi"}])
    assert result.ok is True
    assert result.reason == "done"
    # 评估器必须无 tools、且带 max_tokens
    assert provider.calls[0][1] == []
    assert provider.calls[0][2] == 512


def test_evaluate_invalid_json_raises():
    provider = _FakeProvider("not json")
    with pytest.raises(GoalError):
        PromptGoalEvaluator(provider).evaluate("x", [])
