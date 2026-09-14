import pytest

from blh.core.config import Config
from blh.providers.openai import OpenAIProvider


class FakeMessage:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


class FakeCompletions:
    def __init__(self, payload):
        self.received = None
        self._payload = payload

    def create(self, **kwargs):
        self.received = kwargs
        return type("Resp", (), {
            "choices": [type("Choice", (), {"message": FakeMessage(self._payload)})()]
        })()


class FakeClient:
    def __init__(self, payload):
        self.chat = type("Chat", (), {"completions": FakeCompletions(payload)})()


def make_config():
    return Config(api_key="sk-test", base_url=None, model="test-model", workdir=".")


def test_chat_passes_messages_and_tools():
    payload = {"role": "assistant", "content": "hi", "tool_calls": None}
    client = FakeClient(payload)
    provider = OpenAIProvider(make_config(), client=client)
    tools = [{"type": "function", "function": {"name": "t", "description": "", "parameters": {}}}]
    messages = [{"role": "user", "content": "hello"}]

    result = provider.chat(messages, tools)

    assert result == payload
    assert client.chat.completions.received["model"] == "test-model"
    assert client.chat.completions.received["messages"] == messages
    assert client.chat.completions.received["tools"] == tools


def test_chat_omits_tools_when_empty():
    payload = {"role": "assistant", "content": "hi", "tool_calls": None}
    client = FakeClient(payload)
    provider = OpenAIProvider(make_config(), client=client)

    provider.chat([{"role": "user", "content": "hi"}], [])

    assert client.chat.completions.received["tools"] is None


def test_chat_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    class FakeAPIError(Exception):
        status_code = 500

    class FailingCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise FakeAPIError("server error")

    client = type("C", (), {"chat": type("Chat", (), {"completions": FailingCompletions()})()})()
    provider = OpenAIProvider(make_config(), client=client)

    with pytest.raises(FakeAPIError):
        provider.chat([{"role": "user", "content": "hi"}], [])

    assert client.chat.completions.calls == 5


def test_is_prompt_too_long_matches_400_with_keywords():
    from blh.providers.openai import is_prompt_too_long

    class FakeBadRequest(Exception):
        status_code = 400

    assert is_prompt_too_long(FakeBadRequest("prompt_too_long: ..."))
    assert is_prompt_too_long(FakeBadRequest(
        "This model's maximum context length is 65536"))
    assert is_prompt_too_long(FakeBadRequest("too many tokens in prompt"))
    assert not is_prompt_too_long(FakeBadRequest("invalid api key"))
    assert not is_prompt_too_long(ValueError("prompt_too_long"))  # 无 400


def test_chat_passes_max_tokens_when_provided():
    payload = {"role": "assistant", "content": "hi", "tool_calls": None}
    client = FakeClient(payload)
    provider = OpenAIProvider(make_config(), client=client)
    provider.chat([{"role": "user", "content": "hi"}], [], max_tokens=200)
    assert client.chat.completions.received["max_tokens"] == 200


def test_chat_omits_max_tokens_when_none():
    payload = {"role": "assistant", "content": "hi", "tool_calls": None}
    client = FakeClient(payload)
    provider = OpenAIProvider(make_config(), client=client)
    provider.chat([{"role": "user", "content": "hi"}], [])
    assert "max_tokens" not in client.chat.completions.received
