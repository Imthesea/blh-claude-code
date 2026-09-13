from openai import OpenAI

from ..core.config import Config
from .retry import RetryState, is_retryable, with_retry


class OpenAIProvider:
    def __init__(self, config: Config, client=None):
        self.config = config
        self.client = client or OpenAI(api_key=config.api_key, base_url=config.base_url)

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        def call():
            return self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                tools=tools or None,
            )

        response = with_retry(call, RetryState(), is_retryable)
        return response.choices[0].message.model_dump()
