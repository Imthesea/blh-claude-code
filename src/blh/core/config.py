import os
from dataclasses import dataclass


@dataclass
class Config:
    api_key: str
    base_url: str | None
    model: str
    workdir: str
    bash_timeout: int = 120
    max_output_chars: int = 30000


def load_config(workdir: str | None = None) -> Config:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set")
    return Config(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        model=os.environ.get("BLH_MODEL", "gpt-4o-mini"),
        workdir=workdir or os.getcwd(),
    )
