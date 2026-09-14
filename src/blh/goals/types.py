"""goals 共享数据类型。"""

from dataclasses import dataclass


class GoalError(Exception):
    """goal 命令或评估器无法安全使用。"""


@dataclass
class GoalState:
    condition: str
    iterations: int
    set_at: float
    tokens_at_start: int
    last_reason: str | None = None


@dataclass(frozen=True)
class GoalEvaluation:
    ok: bool
    reason: str
    impossible: bool = False


@dataclass(frozen=True)
class StopDecision:
    action: str
    reason: str = ""
