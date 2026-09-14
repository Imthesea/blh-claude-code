"""GoalController:session 级 goal + Stop hook 决策(同步)。"""

import time

from .types import GoalError, GoalState, StopDecision

MAX_GOAL_LENGTH = 4000
CLEAR_ALIASES = {"clear", "stop", "off", "reset", "none", "cancel"}
DEFAULT_STOP_HOOK_BLOCK_CAP = 8


class GoalController:
    def __init__(self, evaluator, block_cap=DEFAULT_STOP_HOOK_BLOCK_CAP,
                 events=None):
        if block_cap < 1:
            raise GoalError("block_cap must be at least 1")
        self.evaluator = evaluator
        self.block_cap = block_cap
        self.events = events if events is not None else []
        self.active = None
        self.last_status = None
        self.consecutive_blocks = 0

    def begin_query(self):
        self.consecutive_blocks = 0

    def set_goal(self, condition, tokens_at_start=0):
        condition = condition.strip()
        if not condition:
            raise GoalError("goal condition cannot be empty")
        if len(condition) > MAX_GOAL_LENGTH:
            raise GoalError(
                f"goal condition cannot exceed {MAX_GOAL_LENGTH} characters")
        if self.active is not None:
            self._record(active=False, met=False, failed=False,
                         reason="replaced by a new goal")
        self.active = GoalState(condition=condition, iterations=0,
                                set_at=time.time(),
                                tokens_at_start=tokens_at_start)
        self.consecutive_blocks = 0
        self._record(active=True, met=False, failed=False, reason="goal set")
        return self.active

    def clear(self, reason="cleared"):
        if self.active is None:
            return "No goal set"
        condition = self.active.condition
        self._record(active=False, met=False, failed=False, reason=reason)
        self.active = None
        self.consecutive_blocks = 0
        return f"Goal cleared: {condition}"

    def status(self, current_tokens=0):
        if self.active is None:
            if self.last_status and self.last_status.get("met"):
                return (f"Goal achieved: {self.last_status['condition']}\n"
                        f"Reason: {self.last_status.get('reason', '')}")
            if self.last_status and self.last_status.get("failed"):
                return (f"Goal failed: {self.last_status['condition']}\n"
                        f"Reason: {self.last_status.get('reason', '')}")
            return "No goal set"
        elapsed = max(0, int(time.time() - self.active.set_at))
        spent = max(0, current_tokens - self.active.tokens_at_start)
        lines = [f"Goal active: {self.active.condition}",
                 f"Elapsed: {elapsed}s",
                 f"Evaluations: {self.active.iterations}",
                 f"Tokens: {spent}"]
        if self.active.last_reason:
            lines.append(f"Last reason: {self.active.last_reason}")
        return "\n".join(lines)

    def evaluate_after_turn(self, messages, background_running=False):
        if self.active is None:
            return StopDecision("allow")
        if background_running:
            return StopDecision("defer", "background work is still running")

        state = self.active
        try:
            evaluation = self.evaluator.evaluate(state.condition, messages)
        except Exception as error:  # noqa: BLE001 - 评估器异常转 error 决策
            reason = f"{type(error).__name__}: {error}"
            state.last_reason = reason
            self._record(active=True, met=False, failed=False, reason=reason)
            return StopDecision("error", reason)

        state.iterations += 1
        state.last_reason = evaluation.reason

        if evaluation.ok:
            self._record(active=False, met=True, failed=False,
                         reason=evaluation.reason)
            self.active = None
            self.consecutive_blocks = 0
            return StopDecision("achieved", evaluation.reason)

        if evaluation.impossible:
            self._record(active=False, met=False, failed=True,
                         reason=evaluation.reason)
            self.active = None
            self.consecutive_blocks = 0
            return StopDecision("failed", evaluation.reason)

        self.consecutive_blocks += 1
        self._record(active=True, met=False, failed=False,
                     reason=evaluation.reason)
        if self.consecutive_blocks > self.block_cap:
            return StopDecision(
                "limit",
                f"goal remains active, but the Stop hook blocked "
                f"{self.block_cap} consecutive turns")
        return StopDecision("block", evaluation.reason)

    def _record(self, *, active, met, failed, reason):
        state = self.active
        event = {
            "type": "goal_status",
            "condition": state.condition if state else "",
            "active": active,
            "met": met,
            "failed": failed,
            "reason": reason,
            "iterations": state.iterations if state else 0,
            "duration": max(0, time.time() - state.set_at) if state else 0,
        }
        self.events.append(event)
        self.last_status = event

    @classmethod
    def restore(cls, evaluator, events, block_cap=DEFAULT_STOP_HOOK_BLOCK_CAP):
        controller = cls(evaluator=evaluator, block_cap=block_cap,
                         events=list(events))
        for event in reversed(events):
            if event.get("type") != "goal_status":
                continue
            controller.last_status = dict(event)
            if event.get("active"):
                controller.active = GoalState(
                    condition=str(event["condition"]), iterations=0,
                    set_at=time.time(), tokens_at_start=0, last_reason=None)
            break
        return controller
