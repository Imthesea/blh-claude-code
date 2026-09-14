import random

import pytest

from blh.providers.retry import (
    RetryState,
    is_retryable,
    retry_after_seconds,
    retry_delay,
    with_retry,
)


class FakeAPIError(Exception):
    def __init__(self, status_code, headers=None):
        super().__init__(f"status {status_code}")
        self.status_code = status_code
        self._headers = headers or {}

    @property
    def response(self):
        class _Response:
            def __init__(self, headers):
                self.headers = headers
        return _Response(self._headers)


def test_is_retryable():
    assert is_retryable(FakeAPIError(429))
    assert is_retryable(FakeAPIError(500))
    assert is_retryable(FakeAPIError(529))
    assert not is_retryable(FakeAPIError(400))
    assert not is_retryable(ValueError("x"))


def test_retry_after_seconds_from_header():
    assert retry_after_seconds(FakeAPIError(429, {"Retry-After": "3"})) == 3.0


def test_retry_after_seconds_invalid_returns_none():
    assert retry_after_seconds(FakeAPIError(429, {"Retry-After": "x"})) is None


def test_retry_after_seconds_no_response():
    assert retry_after_seconds(ValueError("x")) is None


def test_retry_delay_prefers_retry_after():
    assert retry_delay(1, FakeAPIError(429, {"Retry-After": "7"})) == 7.0


def test_retry_delay_exponential_with_jitter(monkeypatch):
    monkeypatch.setattr(random, "uniform", lambda a, b: 1.0)
    assert retry_delay(1) == 2
    assert retry_delay(2) == 4
    assert retry_delay(10) == 32


def test_with_retry_succeeds_after_failures(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise FakeAPIError(500)
        return "ok"

    assert with_retry(flaky, RetryState(), is_retryable) == "ok"
    assert calls["n"] == 3


def test_with_retry_gives_up_on_non_retryable():
    def bad():
        raise FakeAPIError(400)

    with pytest.raises(FakeAPIError):
        with_retry(bad, RetryState(), is_retryable)


def test_with_retry_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise FakeAPIError(500)

    with pytest.raises(FakeAPIError):
        with_retry(always_fail, RetryState(max_attempts=2), is_retryable)
    assert calls["n"] == 2
