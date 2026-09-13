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
