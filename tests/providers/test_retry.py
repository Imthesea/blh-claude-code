import pytest

from blh.providers.retry import RetryState, is_retryable, retry_delay, with_retry


class FakeAPIError(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


def test_is_retryable():
    assert is_retryable(FakeAPIError(429))
    assert is_retryable(FakeAPIError(500))
    assert is_retryable(FakeAPIError(529))
    assert not is_retryable(FakeAPIError(400))
    assert not is_retryable(ValueError("x"))


def test_retry_delay_exponential_capped():
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
