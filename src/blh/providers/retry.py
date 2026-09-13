import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass
class RetryState:
    attempts: int = 0
    max_attempts: int = 5


def retry_delay(attempt: int) -> float:
    """指数退避,封顶 32s。

    已知限制:M0 不读取 429 响应的 Retry-After 头(计划/设计承诺项,
    推迟到 M1 实现)。
    """
    return min(2**attempt, 32)


def is_retryable(e: Exception) -> bool:
    status = getattr(e, "status_code", None)
    return status == 429 or (status is not None and status >= 500)


def with_retry(
    fn: Callable[[], T],
    state: RetryState,
    should_retry: Callable[[Exception], bool],
) -> T:
    while True:
        try:
            return fn()
        except Exception as e:
            state.attempts += 1
            if state.attempts >= state.max_attempts or not should_retry(e):
                raise
            time.sleep(retry_delay(state.attempts))
