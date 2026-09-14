import pytest

from blh.goals.controller import GoalController
from blh.goals.types import GoalError, GoalEvaluation


class _Evaluator:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def evaluate(self, condition, messages):
        self.calls += 1
        return self._results.pop(0)


def test_no_goal_allow():
    ctrl = GoalController(_Evaluator([]))
    assert ctrl.evaluate_after_turn([]).action == "allow"


def test_ok_achieved():
    ctrl = GoalController(_Evaluator([GoalEvaluation(True, "done")]))
    ctrl.set_goal("do it")
    decision = ctrl.evaluate_after_turn([])
    assert decision.action == "achieved"
    assert ctrl.active is None


def test_impossible_failed():
    ctrl = GoalController(_Evaluator([GoalEvaluation(False, "cannot", impossible=True)]))
    ctrl.set_goal("do it")
    assert ctrl.evaluate_after_turn([]).action == "failed"


def test_block_then_limit():
    results = [GoalEvaluation(False, "still missing")] * 20
    ctrl = GoalController(_Evaluator(results), block_cap=8)
    ctrl.set_goal("do it")
    actions = [ctrl.evaluate_after_turn([]).action for _ in range(9)]
    assert actions[:8] == ["block"] * 8
    assert actions[8] == "limit"


def test_clear():
    ctrl = GoalController(_Evaluator([]))
    ctrl.set_goal("do it")
    assert "cleared" in ctrl.clear().lower()
    assert ctrl.active is None


def test_set_goal_empty_raises():
    with pytest.raises(GoalError):
        GoalController(_Evaluator([])).set_goal("   ")


def test_background_defer():
    ctrl = GoalController(_Evaluator([GoalEvaluation(False, "x")]))
    ctrl.set_goal("do it")
    assert ctrl.evaluate_after_turn([], background_running=True).action == "defer"
