import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass
class RetryState:
    attempts: int = 0
    max_attempts: int = 5


def retry_after_seconds(error: Exception) -> float | None:
    """读取 429 响应的 Retry-After 头(秒),无则返回 None。"""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def retry_delay(attempt: int, error: Exception | None = None) -> float:
    """指数退避 + 乘法抖动,封顶 32s;429 的 Retry-After 优先。"""
    retry_after = retry_after_seconds(error) if error is not None else None
    if retry_after is not None and retry_after > 0:
        return retry_after
    base = min(2**attempt, 32)
    return base * random.uniform(0.5, 1.5)


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
            time.sleep(retry_delay(state.attempts, e))
