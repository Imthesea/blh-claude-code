from openai import OpenAI

from ..core.config import Config
from .retry import RetryState, is_retryable, with_retry


class OpenAIProvider:
    def __init__(self, config: Config, client=None):
        self.config = config
        self.client = client or OpenAI(api_key=config.api_key, base_url=config.base_url)

    def chat(self, messages: list[dict], tools: list[dict],
             max_tokens: int | None = None) -> dict:
        def call():
            kwargs = {"model": self.config.model, "messages": messages,
                      "tools": tools or None}
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            return self.client.chat.completions.create(**kwargs)

        response = with_retry(call, RetryState(), is_retryable)
        return response.choices[0].message.model_dump()


def is_prompt_too_long(error: Exception) -> bool:
    """启发式判定上下文超长:HTTP 400 + 错误体关键词(各兼容端格式不一)。"""
    if getattr(error, "status_code", None) != 400:
        return False
    text = str(error).lower()
    return any(keyword in text for keyword in (
        "prompt_too_long", "too many tokens", "context length",
        "context_length_exceeded", "maximum context", "reduce the length"))
