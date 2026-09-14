import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    """配置解析失败。"""


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


def _find_config(start: Path) -> list[Path]:
    """按「低优先级在前」返回配置文件:用户级 → 项目级。"""
    files: list[Path] = []
    user = Path.home() / ".config" / "blh" / "config.yaml"
    if user.is_file():
        files.append(user)
    for directory in (start, *start.parents):
        candidate = directory / ".blh.yaml"
        if candidate.is_file():
            files.append(candidate)
            break
    return files


def _to_int(value: object, key: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ConfigError(f"invalid int for {key}: {value!r}")


def load_config(workdir: str | None = None,
                cli: dict | None = None) -> Config:
    dotenv = _find_dotenv(Path.cwd())
    if dotenv:
        load_dotenv(dotenv)  # 已存在的环境变量优先,不覆盖

    cli = cli or {}

    file_values: dict = {}
    for path in _find_config(Path.cwd()):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ConfigError(f"config {path} must be a mapping")
        file_values.update(data)

    def get(key: str, env_name: str | None, default: object) -> object:
        if key in cli and cli[key] is not None:
            return cli[key]
        if env_name is not None:
            env = os.environ.get(env_name)
            if env is not None:
                return env
        if key in file_values and file_values[key] is not None:
            return file_values[key]
        return default

    api_key = get("api_key", "OPENAI_API_KEY", "")
    base_url = get("base_url", "OPENAI_BASE_URL", None)
    model = get("model", "BLH_MODEL", "gpt-4o-mini")
    workdir_value = get("workdir", None, workdir or os.getcwd())
    bash_timeout = _to_int(get("bash_timeout", "BLH_BASH_TIMEOUT", 120),
                           "bash_timeout")
    max_output_chars = _to_int(
        get("max_output_chars", "BLH_MAX_OUTPUT_CHARS", 30000),
        "max_output_chars")

    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set")

    return Config(
        api_key=api_key,
        base_url=base_url,
        model=model,
        workdir=workdir_value,
        bash_timeout=bash_timeout,
        max_output_chars=max_output_chars,
    )
