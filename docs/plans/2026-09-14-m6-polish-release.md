# blh-claude-code M6:打磨与发布 实现计划

- **日期**:2026-09-14
- **依据**:`docs/2026-09-14-m6-polish-release-design.md`
- **方法**:TDD(config/retry),README/打包为文档与验证任务

## 任务总览

| # | 任务 | 产物 |
|---|---|---|
| 1 | 配置:Config 分层加载(文件 + env + CLI) | `core/config.py` |
| 2 | CLI 参数接入 `--model/--base-url/--workdir/...` | `cli/main.py` |
| 3 | retry:Retry-After + 抖动 | `providers/retry.py` |
| 4 | README | `README.md` |
| 5 | pyproject 元数据 + 打包验证 | `pyproject.toml` |
| 6 | 收尾验证 | pytest + ruff + uv build |

---

## 任务 1:配置分层加载(`core/config.py`)

### 1.1 失败测试 `tests/core/test_config.py`

```python
import pytest

from blh.core.config import Config, ConfigError, load_config


def test_defaults_when_nothing_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_config()


def test_env_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("BLH_MODEL", "env-model")
    cfg = load_config()
    assert cfg.model == "env-model"


def test_file_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    (tmp_path / ".blh.yaml").write_text(
        'model: file-model\nmax_output_chars: 123\n', encoding="utf-8")
    cfg = load_config()
    assert cfg.model == "file-model"
    assert cfg.max_output_chars == 123


def test_env_overrides_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("BLH_MODEL", "env-model")
    (tmp_path / ".blh.yaml").write_text('model: file-model\n', encoding="utf-8")
    cfg = load_config()
    assert cfg.model == "env-model"


def test_cli_overrides_all(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("BLH_MODEL", "env-model")
    (tmp_path / ".blh.yaml").write_text('model: file-model\n', encoding="utf-8")
    cfg = load_config(cli={"model": "cli-model"})
    assert cfg.model == "cli-model"


def test_invalid_int_raises_config_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("BLH_BASH_TIMEOUT", "abc")
    with pytest.raises(ConfigError):
        load_config()
```

### 1.2 实现

- 新增 `ConfigError(Exception)`。
- `_find_config(start) -> list[Path]`:按「低优先级在前」返回 `[用户级 ~/.config/blh/config.yaml, 项目级 .blh.yaml]`,仅含存在的文件。
- `load_config(workdir=None, cli=None)` 按设计 §3.2 分层合成;`bash_timeout`/`max_output_chars` 用 `_to_int(value, source, key)` 转换,失败抛 `ConfigError`。

### 1.3 验证

```powershell
uv run pytest tests/core/test_config.py -q
```

### 1.4 commit

```
feat(config): add layered config loading with file/env/cli precedence
```

---

## 任务 2:CLI 参数接入(`cli/main.py`)

### 2.1 失败测试(追加 `tests/cli/test_main.py`)

断言 `main()` 的 argparse 在传入 `--model x` 时,`build_harness` 收到的 `load_config` 得到 `cli={"model": "x"}`。用 monkeypatch 替换 `build_harness` 捕获 `workdir`/`cli` 透传,或直接测 `load_config(cli=...)` 已由任务 1 覆盖 —— 本任务重点验证 `main` 把 CLI 参数正确转成 `cli` 字典并传入。

### 2.2 实现

`main()` 增加参数:

```python
parser.add_argument("--model")
parser.add_argument("--base-url", dest="base_url")
parser.add_argument("--workdir")
parser.add_argument("--bash-timeout", dest="bash_timeout", type=int)
parser.add_argument("--max-output-chars", dest="max_output_chars", type=int)
```

`build_harness(workdir, cli)` 增加 `cli` 形参,内部 `load_config(workdir, cli)`。`main` 里组装非 None 的 `cli` 字典传入 `build_harness`。

### 2.3 验证

```powershell
uv run pytest tests/cli/test_main.py -q
```

### 2.4 commit

```
feat(cli): expose model/base-url/workdir/timeout flags
```

---

## 任务 3:retry(`providers/retry.py`)

### 3.1 失败测试 `tests/providers/test_retry.py`

```python
import time

import pytest

from blh.providers.retry import (retry_after_seconds, retry_delay,
                                 is_retryable, with_retry)


class _Err(Exception):
    def __init__(self, status_code=None, headers=None):
        self.status_code = status_code
        self._headers = headers

    @property
    def response(self):
        class R:
            def __init__(self, headers):
                self.headers = headers
        return R(self._headers or {})


def test_retry_after_seconds_from_header():
    assert retry_after_seconds(_Err(headers={"Retry-After": "3"})) == 3.0


def test_retry_after_seconds_invalid_returns_none():
    assert retry_after_seconds(_Err(headers={"Retry-After": "x"})) is None


def test_retry_after_seconds_no_response():
    assert retry_after_seconds(Exception("x")) is None


def test_retry_delay_prefers_retry_after():
    assert retry_delay(1, _Err(headers={"Retry-After": "7"})) == 7.0


def test_retry_delay_bounded_and_jittered(monkeypatch):
    monkeypatch.setattr("random.uniform", lambda a, b: 1.0)
    assert retry_delay(10) == 32.0


def test_with_retry_gives_up():
    calls = []
    def fn():
        calls.append(1)
        raise _Err(500)
    with pytest.raises(_Err):
        with_retry(fn, __import__("blh.providers.retry", fromlist=["RetryState"]).RetryState(max_attempts=2), is_retryable)
    assert len(calls) == 2
```

### 3.2 实现

按设计 §4:`retry_after_seconds` / `retry_delay(attempt, error=None)` / `with_retry` 传 error 进 `retry_delay`。

### 3.3 验证

```powershell
uv run pytest tests/providers/test_retry.py -q
```

### 3.4 commit

```
fix(providers): honor Retry-After and add backoff jitter
```

---

## 任务 4:README

新建 `README.md`,按设计 §5 内容编写。无单测。

```powershell
# 人工检查
```

### commit

```
docs: add README with install and configuration guide
```

---

## 任务 5:pyproject 元数据 + 打包验证

- 补齐 `readme = "README.md"`、`license`、`classifiers`、`keywords`(按仓库现状)。
- 验证:

```powershell
uv build
```

产出 `dist/*.whl` 与 `dist/*.tar.gz`;随后:

```powershell
uv run blh --help
```

确认入口可用。

### commit

```
chore(packaging): complete project metadata for release
```

---

## 任务 6:收尾验证

```powershell
uv run pytest -q
uv run ruff check src/blh tests
uv build
```

全部通过后,更新 `docs/2026-09-14-m6-polish-release-design.md` 状态为「已实施」,汇总 M6 完成。
