import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    api_key: str
    base_url: str | None
    model: str
    workdir: str
    bash_timeout: int = 120
    max_output_chars: int = 30000


def _find_dotenv(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_config(workdir: str | None = None) -> Config:
    dotenv = _find_dotenv(Path.cwd())
    if dotenv:
        load_dotenv(dotenv)  # 已存在的环境变量优先,不覆盖
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set")
    return Config(
        api_key=api_key,
        base_url=os.environ.get("OPENAI_BASE_URL") or None,
        model=os.environ.get("BLH_MODEL", "gpt-4o-mini"),
        workdir=workdir or os.getcwd(),
    )
