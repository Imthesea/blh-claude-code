# blh-claude-code M0:骨架与最小闭环 实现计划

> **面向 AI 代理的工作者:** 必需子技能:使用 superpowers:subagent-driven-development(推荐)或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框(`- [ ]`)语法来跟踪进度。

**目标:** 搭建可安装的 `blh` CLI,跑通"用户输入 → OpenAI 兼容 API → 工具调用 → 权限审批 → 结果返回"的最小闭环。

**架构:** 四层骨架——`cli`(REPL/-p)→ `core`(Harness + agent loop + hook 总线)→ `tools`/`security`(工具注册表 + 权限 hook)→ `providers`(OpenAI 兼容接入 + 重试)。权限作为 `PreToolUse` hook 实现,不硬编码在 dispatch。

**技术栈:** Python 3.11+、openai SDK、pytest、ruff;src 布局,setuptools 打包。

**设计文档:** `../2026-09-13-blh-claude-code-design.md`

**范围说明:** 本计划仅覆盖 M0。M1(上下文与规划)~ M6(发布)在各自里程碑开始前另行编写计划。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `pyproject.toml` | 打包、依赖、entry point `blh` |
| `src/blh/__init__.py` | 包标识(空) |
| `src/blh/core/config.py` | 环境变量配置加载 |
| `src/blh/core/hooks.py` | HookBus:注册/触发/首个拦截 |
| `src/blh/core/harness.py` | Harness:装配各部件,驱动单轮 |
| `src/blh/core/loop.py` | agent_loop 主循环 + 助手文本提取 |
| `src/blh/providers/retry.py` | 指数退避重试(429/5xx,读 Retry-After) |
| `src/blh/providers/openai.py` | OpenAIProvider:chat(messages, tools) |
| `src/blh/tools/registry.py` | Tool 数据类 + ToolRegistry(schemas/dispatch) |
| `src/blh/tools/bash.py` | run_bash(超时/输出截断) |
| `src/blh/tools/files.py` | safe_path 沙箱 + read/write/edit |
| `src/blh/tools/glob.py` | glob_files |
| `src/blh/tools/__init__.py` | register_builtin_tools(5 个内置工具) |
| `src/blh/security/rules.py` | PermissionRule + 匹配 |
| `src/blh/security/approval.py` | 权限 PreToolUse hook 工厂 |
| `src/blh/cli/main.py` | argparse 入口,装配 Harness |
| `src/blh/cli/repl.py` | 交互循环 |
| `tests/` | 镜像 src 结构 |

---

### 任务 1:项目骨架与打包

**文件:**
- 创建:`pyproject.toml`
- 创建:`src/blh/__init__.py`(空)
- 创建:`src/blh/core/__init__.py`、`src/blh/providers/__init__.py`、`src/blh/security/__init__.py`、`src/blh/cli/__init__.py`(均空)
- 创建:`tests/__init__.py`(空)
- 测试:`tests/test_smoke.py`

- [ ] **步骤 1:初始化 git 并编写失败测试**

```bash
cd F:\allProject\myProject\blh-claude-code
git init
```

```python
# tests/test_smoke.py
def test_package_importable():
    import blh
    assert blh is not None
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pip install -e ".[dev]"
pytest tests/test_smoke.py -v
```

预期:第一次 `pip install -e` 因无 `pyproject.toml` 失败 / 测试因 `import blh` 失败。

- [ ] **步骤 3:编写打包配置**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "blh-claude-code"
version = "0.1.0"
description = "A coding agent CLI built on OpenAI-compatible APIs"
requires-python = ">=3.11"
dependencies = ["openai>=1.40"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5"]

[project.scripts]
blh = "blh.cli.main:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
markers = ["live: tests that call a real API (deselect with -m 'not live')"]
```

```bash
pip install -e ".[dev]"
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/test_smoke.py -v
```

预期:PASS。

- [ ] **步骤 5:Commit**

```bash
git add pyproject.toml src tests
git commit -m "chore: project skeleton with src layout and packaging"
```

---

### 任务 2:core/config

**文件:**
- 创建:`src/blh/core/config.py`
- 测试:`tests/core/test_config.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/core/test_config.py
import pytest
from blh.core.config import Config, load_config


def test_load_config_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:9999/v1")
    monkeypatch.setenv("BLH_MODEL", "test-model")
    cfg = load_config(workdir=str(tmp_path))
    assert cfg.api_key == "sk-test"
    assert cfg.base_url == "http://localhost:9999/v1"
    assert cfg.model == "test-model"
    assert cfg.workdir == str(tmp_path)


def test_load_config_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        load_config()


def test_base_url_defaults_to_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    assert load_config().base_url is None
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/core/test_config.py -v
```

预期:FAIL,`ModuleNotFoundError: No module named 'blh.core.config'`。

- [ ] **步骤 3:实现**

```python
# src/blh/core/config.py
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
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/core/test_config.py -v
```

预期:3 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/core/config.py tests/core/test_config.py
git commit -m "feat(core): env-based config loading"
```

---

### 任务 3:providers/retry

**文件:**
- 创建:`src/blh/providers/retry.py`
- 测试:`tests/providers/test_retry.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/providers/test_retry.py
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
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/providers/test_retry.py -v
```

预期:FAIL,`ModuleNotFoundError`。

- [ ] **步骤 3:实现**

```python
# src/blh/providers/retry.py
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass
class RetryState:
    attempts: int = 0
    max_attempts: int = 5


def retry_delay(attempt: int) -> float:
    return min(2 ** attempt, 32)


def is_retryable(e: Exception) -> bool:
    status = getattr(e, "status_code", None)
    return status == 429 or (status is not None and status >= 500)


def with_retry(fn: Callable[[], T], state: RetryState, should_retry: Callable[[Exception], bool]) -> T:
    while True:
        try:
            return fn()
        except Exception as e:
            state.attempts += 1
            if state.attempts >= state.max_attempts or not should_retry(e):
                raise
            time.sleep(retry_delay(state.attempts))
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/providers/test_retry.py -v
```

预期:4 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/providers/retry.py tests/providers/test_retry.py
git commit -m "feat(providers): exponential backoff retry for 429/5xx"
```

---

### 任务 4:providers/openai

**文件:**
- 创建:`src/blh/providers/openai.py`
- 测试:`tests/providers/test_openai.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/providers/test_openai.py
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
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/providers/test_openai.py -v
```

预期:FAIL,`ModuleNotFoundError`。

- [ ] **步骤 3:实现**

```python
# src/blh/providers/openai.py
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
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/providers/test_openai.py -v
```

预期:2 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/providers/openai.py tests/providers/test_openai.py
git commit -m "feat(providers): OpenAI-compatible chat wrapper returning message dicts"
```

---

### 任务 5:tools/registry

**文件:**
- 创建:`src/blh/tools/registry.py`
- 测试:`tests/tools/test_registry.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/tools/test_registry.py
import json

from blh.tools.registry import Tool, ToolRegistry


def make_tool(name="echo"):
    return Tool(
        name=name,
        description="echo input",
        parameters={"type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"]},
        handler=lambda text: text,
    )


def test_register_and_schemas():
    reg = ToolRegistry()
    reg.register(make_tool())
    schemas = reg.schemas()
    assert schemas == [{
        "type": "function",
        "function": {
            "name": "echo",
            "description": "echo input",
            "parameters": {"type": "object",
                           "properties": {"text": {"type": "string"}},
                           "required": ["text"]},
        },
    }]


def test_dispatch_calls_handler():
    reg = ToolRegistry()
    reg.register(make_tool())
    assert reg.dispatch("echo", json.dumps({"text": "hi"})) == "hi"


def test_dispatch_unknown_tool():
    assert "unknown tool" in ToolRegistry().dispatch("nope", "{}")


def test_dispatch_invalid_json():
    reg = ToolRegistry()
    reg.register(make_tool())
    assert "invalid tool arguments" in reg.dispatch("echo", "{bad json")


def test_dispatch_handler_exception_returns_error():
    reg = ToolRegistry()
    reg.register(Tool("boom", "", {}, handler=lambda: 1 / 0))
    assert "failed" in reg.dispatch("boom", "{}")
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/tools/test_registry.py -v
```

预期:FAIL,`ModuleNotFoundError`。

- [ ] **步骤 3:实现**

```python
# src/blh/tools/registry.py
import json
from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema
    handler: Callable[..., str]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [
            {"type": "function",
             "function": {"name": t.name,
                          "description": t.description,
                          "parameters": t.parameters}}
            for t in self._tools.values()
        ]

    def dispatch(self, name: str, arguments_json: str) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"error: unknown tool '{name}'"
        try:
            args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as e:
            return f"error: invalid tool arguments: {e}"
        try:
            return tool.handler(**args)
        except Exception as e:
            return f"error: tool '{name}' failed: {e}"
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/tools/test_registry.py -v
```

预期:5 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/tools/registry.py tests/tools/test_registry.py
git commit -m "feat(tools): tool registry with OpenAI function-calling schemas"
```

---

### 任务 6:tools/files(safe_path + read/write/edit)

**文件:**
- 创建:`src/blh/tools/files.py`
- 测试:`tests/tools/test_files.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/tools/test_files.py
import pytest
from blh.tools.files import PathEscapeError, edit_file, read_file, safe_path, write_file


def test_safe_path_inside(tmp_path):
    p = safe_path("a/b.txt", str(tmp_path))
    assert str(p).startswith(str(tmp_path.resolve()))


def test_safe_path_escape_rejected(tmp_path):
    with pytest.raises(PathEscapeError):
        safe_path("../outside.txt", str(tmp_path))
    with pytest.raises(PathEscapeError):
        safe_path("C:/Windows/System32/drivers/etc/hosts", str(tmp_path))


def test_write_then_read(tmp_path):
    wd = str(tmp_path)
    write_file("notes.txt", "line1\nline2\nline3", wd)
    assert read_file("notes.txt", wd) == "1\tline1\n2\tline2\n3\tline3"


def test_read_offset_limit(tmp_path):
    wd = str(tmp_path)
    write_file("n.txt", "a\nb\nc\nd", wd)
    assert read_file("n.txt", wd, offset=2, limit=2) == "2\tb\n3\tc"


def test_edit_unique_replacement(tmp_path):
    wd = str(tmp_path)
    write_file("e.txt", "foo bar foo", wd)
    result = edit_file("e.txt", "bar", "baz", wd)
    assert "edited" in result
    assert read_file("e.txt", wd) == "1\tfoo baz foo"


def test_edit_non_unique_rejected(tmp_path):
    wd = str(tmp_path)
    write_file("e2.txt", "foo foo", wd)
    assert "2 times" in edit_file("e2.txt", "foo", "x", wd)
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/tools/test_files.py -v
```

预期:FAIL,`ModuleNotFoundError`。

- [ ] **步骤 3:实现**

```python
# src/blh/tools/files.py
from pathlib import Path


class PathEscapeError(Exception):
    pass


def safe_path(path: str, workdir: str) -> Path:
    root = Path(workdir).resolve()
    raw = Path(path)
    p = raw.resolve() if raw.is_absolute() else (root / path).resolve()
    if p != root and root not in p.parents:
        raise PathEscapeError(f"path escapes workdir: {path}")
    return p


def read_file(path: str, workdir: str, offset: int = 1, limit: int | None = None) -> str:
    p = safe_path(path, workdir)
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(offset - 1, 0)
    selected = lines[start:] if limit is None else lines[start:start + limit]
    return "\n".join(f"{i + start + 1}\t{line}" for i, line in enumerate(selected))


def write_file(path: str, content: str, workdir: str) -> str:
    p = safe_path(path, workdir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {p}"


def edit_file(path: str, old_text: str, new_text: str, workdir: str) -> str:
    p = safe_path(path, workdir)
    text = p.read_text(encoding="utf-8", errors="replace")
    count = text.count(old_text)
    if count != 1:
        return f"error: old_text occurs {count} times (must be exactly 1)"
    p.write_text(text.replace(old_text, new_text), encoding="utf-8")
    return f"edited {p}"
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/tools/test_files.py -v
```

预期:6 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/tools/files.py tests/tools/test_files.py
git commit -m "feat(tools): sandboxed file read/write/edit tools"
```

---

### 任务 7:tools/bash + tools/glob

**文件:**
- 创建:`src/blh/tools/bash.py`
- 创建:`src/blh/tools/glob.py`
- 测试:`tests/tools/test_bash.py`、`tests/tools/test_glob.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/tools/test_bash.py
import sys
from blh.tools.bash import run_bash


def test_run_bash_captures_output(tmp_path):
    out = run_bash("echo hello", str(tmp_path))
    assert "hello" in out


def test_run_bash_runs_in_workdir(tmp_path):
    marker = tmp_path / "marker.txt"
    marker.write_text("x")
    cmd = "dir marker.txt /b" if sys.platform == "win32" else "ls marker.txt"
    assert "marker.txt" in run_bash(cmd, str(tmp_path))


def test_run_bash_truncates_long_output(tmp_path):
    out = run_bash(f"{sys.executable} -c \"print('x' * 50000)\"", str(tmp_path), max_output=1000)
    assert len(out) < 1200
    assert "truncated" in out


def test_run_bash_timeout(tmp_path):
    cmd = f"{sys.executable} -c \"import time; time.sleep(10)\""
    assert "timed out" in run_bash(cmd, str(tmp_path), timeout=1)
```

```python
# tests/tools/test_glob.py
from blh.tools.glob import glob_files


def test_glob_matches_relative(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("")
    out = glob_files("**/*.py", str(tmp_path))
    assert "a.py" in out
    assert "b.py" in out


def test_glob_no_matches(tmp_path):
    assert glob_files("*.rs", str(tmp_path)) == "(no matches)"
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/tools/test_bash.py tests/tools/test_glob.py -v
```

预期:FAIL,`ModuleNotFoundError`。

- [ ] **步骤 3:实现**

```python
# src/blh/tools/bash.py
import subprocess


def run_bash(command: str, workdir: str, timeout: int = 120, max_output: int = 30000) -> str:
    try:
        proc = subprocess.run(
            command, shell=True, cwd=workdir,
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return f"error: command timed out after {timeout}s"
    output = (proc.stdout or "") + (proc.stderr or "")
    if len(output) > max_output:
        output = output[:max_output] + f"\n... [truncated, {len(output)} chars total]"
    return output or f"(exit code {proc.returncode})"
```

```python
# src/blh/tools/glob.py
from pathlib import Path


def glob_files(pattern: str, workdir: str) -> str:
    root = Path(workdir)
    matches = sorted(p for p in root.glob(pattern) if p.is_file())
    if not matches:
        return "(no matches)"
    return "\n".join(str(p.relative_to(root)) for p in matches[:200])
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/tools/test_bash.py tests/tools/test_glob.py -v
```

预期:6 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/tools/bash.py src/blh/tools/glob.py tests/tools/test_bash.py tests/tools/test_glob.py
git commit -m "feat(tools): bash execution with timeout/truncation and glob search"
```

---

### 任务 8:tools/__init__.py(register_builtin_tools)

**文件:**
- 修改:`src/blh/tools/__init__.py`
- 测试:`tests/tools/test_builtin.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/tools/test_builtin.py
import json

from blh.core.config import Config
from blh.tools import register_builtin_tools
from blh.tools.registry import ToolRegistry


def make_registry(tmp_path):
    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    reg = ToolRegistry()
    register_builtin_tools(reg, cfg)
    return reg


def test_five_tools_registered(tmp_path):
    names = [s["function"]["name"] for s in make_registry(tmp_path).schemas()]
    assert sorted(names) == ["bash", "edit_file", "glob", "read_file", "write_file"]


def test_builtin_dispatch_roundtrip(tmp_path):
    reg = make_registry(tmp_path)
    reg.dispatch("write_file", json.dumps({"path": "x.txt", "content": "hello"}))
    out = reg.dispatch("read_file", json.dumps({"path": "x.txt"}))
    assert "hello" in out
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/tools/test_builtin.py -v
```

预期:FAIL,`ImportError: cannot import name 'register_builtin_tools'`。

- [ ] **步骤 3:实现**

```python
# src/blh/tools/__init__.py
from ..core.config import Config
from . import bash as bash_mod
from . import files as files_mod
from . import glob as glob_mod
from .registry import Tool, ToolRegistry


def register_builtin_tools(registry: ToolRegistry, config: Config) -> None:
    wd = config.workdir
    registry.register(Tool(
        name="bash",
        description="Run a shell command in the workdir. Returns stdout+stderr.",
        parameters={"type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"]},
        handler=lambda command: bash_mod.run_bash(
            command, wd, config.bash_timeout, config.max_output_chars),
    ))
    registry.register(Tool(
        name="read_file",
        description="Read a file with line numbers. offset/limit select a line range.",
        parameters={"type": "object",
                    "properties": {"path": {"type": "string"},
                                   "offset": {"type": "integer"},
                                   "limit": {"type": "integer"}},
                    "required": ["path"]},
        handler=lambda path, offset=1, limit=None: files_mod.read_file(path, wd, offset, limit),
    ))
    registry.register(Tool(
        name="write_file",
        description="Write content to a file, creating parent directories.",
        parameters={"type": "object",
                    "properties": {"path": {"type": "string"},
                                   "content": {"type": "string"}},
                    "required": ["path", "content"]},
        handler=lambda path, content: files_mod.write_file(path, content, wd),
    ))
    registry.register(Tool(
        name="edit_file",
        description="Replace old_text with new_text. old_text must occur exactly once.",
        parameters={"type": "object",
                    "properties": {"path": {"type": "string"},
                                   "old_text": {"type": "string"},
                                   "new_text": {"type": "string"}},
                    "required": ["path", "old_text", "new_text"]},
        handler=lambda path, old_text, new_text: files_mod.edit_file(path, old_text, new_text, wd),
    ))
    registry.register(Tool(
        name="glob",
        description="Find files matching a glob pattern, relative to workdir.",
        parameters={"type": "object",
                    "properties": {"pattern": {"type": "string"}},
                    "required": ["pattern"]},
        handler=lambda pattern: glob_mod.glob_files(pattern, wd),
    ))
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/tools/test_builtin.py -v
```

预期:2 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/tools/__init__.py tests/tools/test_builtin.py
git commit -m "feat(tools): register five builtin tools bound to workdir"
```

---

### 任务 9:security/rules + security/approval

**文件:**
- 创建:`src/blh/security/rules.py`
- 创建:`src/blh/security/approval.py`
- 测试:`tests/security/test_rules.py`、`tests/security/test_approval.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/security/test_rules.py
from blh.security.rules import DEFAULT_RULES, PermissionRule, match_rule


def test_first_matching_rule_wins():
    rules = [PermissionRule("bash", "git *", "allow"),
             PermissionRule("bash", "*", "ask")]
    assert match_rule(rules, "bash", "git status") == "allow"
    assert match_rule(rules, "bash", "make build") == "ask"


def test_tool_field_filters():
    rules = [PermissionRule("write_file", "*", "deny")]
    assert match_rule(rules, "bash", "ls") == "ask"  # 无匹配规则时默认 ask


def test_wildcard_tool_matches_any():
    rules = [PermissionRule("*", "*", "allow")]
    assert match_rule(rules, "read_file", "x.py") == "allow"


def test_default_rules_deny_force_push():
    assert match_rule(DEFAULT_RULES, "bash", "git push --force origin main") == "deny"
    assert match_rule(DEFAULT_RULES, "bash", "ls -la") == "ask"
    assert match_rule(DEFAULT_RULES, "read_file", "a.py") == "allow"
```

```python
# tests/security/test_approval.py
from blh.security.approval import make_permission_hook
from blh.security.rules import PermissionRule


def make_hook(rules, answers=None):
    asked = []
    answers = iter(answers or [])

    def ask_fn(prompt):
        asked.append(prompt)
        return next(answers, "n")

    return make_permission_hook(rules, "/wd", ask_fn=ask_fn), asked


def test_allow_returns_none():
    hook, asked = make_hook([PermissionRule("*", "*", "allow")])
    assert hook({"name": "bash", "input": {"command": "ls"}}) is None
    assert asked == []


def test_deny_returns_reason():
    hook, _ = make_hook([PermissionRule("bash", "rm *", "deny")])
    result = hook({"name": "bash", "input": {"command": "rm -rf x"}})
    assert "denied by permission rule" in result


def test_ask_user_approves():
    hook, _ = make_hook([PermissionRule("bash", "*", "ask")], answers=["y"])
    assert hook({"name": "bash", "input": {"command": "make"}}) is None


def test_ask_user_rejects():
    hook, _ = make_hook([PermissionRule("bash", "*", "ask")], answers=["n"])
    assert hook({"name": "bash", "input": {"command": "make"}}) == "denied by user"


def test_file_tools_use_path_as_target():
    hook, asked = make_hook([PermissionRule("*", "*", "ask")], answers=["y"])
    hook({"name": "write_file", "input": {"path": "a.txt", "content": "x"}})
    assert "a.txt" in asked[0]
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/security/ -v
```

预期:FAIL,`ModuleNotFoundError`。

- [ ] **步骤 3:实现**

```python
# src/blh/security/rules.py
import fnmatch
from dataclasses import dataclass


@dataclass
class PermissionRule:
    tool: str      # 工具名或 "*"
    pattern: str   # 目标 fnmatch 模式(bash 命令 / 文件路径)
    action: str    # "allow" | "ask" | "deny"


DEFAULT_RULES = [
    PermissionRule("bash", "git push --force*", "deny"),
    PermissionRule("bash", "rm -rf /*", "deny"),
    PermissionRule("bash", "*", "ask"),
    PermissionRule("*", "*", "allow"),
]


def match_rule(rules: list[PermissionRule], tool: str, target: str) -> str:
    for rule in rules:
        if rule.tool not in (tool, "*"):
            continue
        if fnmatch.fnmatch(target, rule.pattern):
            return rule.action
    return "ask"
```

```python
# src/blh/security/approval.py
from typing import Callable

from .rules import PermissionRule, match_rule


def make_permission_hook(rules: list[PermissionRule], workdir: str,
                         ask_fn: Callable[[str], str] = input) -> Callable[[dict], str | None]:
    """生成 PreToolUse hook:返回 None 放行,返回字符串则作为拒绝原因。"""

    def permission_hook(event: dict) -> str | None:
        tool = event["name"]
        args = event["input"]
        target = args.get("command") or args.get("path") or ""
        action = match_rule(rules, tool, target)
        if action == "allow":
            return None
        if action == "deny":
            return f"denied by permission rule ({tool}: {target})"
        answer = ask_fn(f"allow {tool}({target})? [y/N] ")
        if answer.strip().lower() in ("y", "yes"):
            return None
        return "denied by user"

    return permission_hook
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/security/ -v
```

预期:9 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/security tests/security
git commit -m "feat(security): permission rules engine with PreToolUse approval hook"
```

---

### 任务 10:core/hooks

**文件:**
- 创建:`src/blh/core/hooks.py`
- 测试:`tests/core/test_hooks.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/core/test_hooks.py
from blh.core.hooks import HookBus


def test_trigger_calls_in_registration_order():
    bus = HookBus()
    order = []
    bus.register("Stop", lambda: order.append("a"))
    bus.register("Stop", lambda: order.append("b"))
    bus.trigger("Stop")
    assert order == ["a", "b"]


def test_trigger_collects_results():
    bus = HookBus()
    bus.register("E", lambda x: x + 1)
    bus.register("E", lambda x: x + 2)
    assert bus.trigger("E", 0) == [1, 2]


def test_first_block_returns_first_non_none():
    bus = HookBus()
    bus.register("PreToolUse", lambda e: None)
    bus.register("PreToolUse", lambda e: "blocked")
    bus.register("PreToolUse", lambda e: "never reached")
    assert bus.first_block("PreToolUse", {}) == "blocked"


def test_first_block_none_when_no_hook():
    assert HookBus().first_block("PreToolUse", {}) is None
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/core/test_hooks.py -v
```

预期:FAIL,`ModuleNotFoundError`。

- [ ] **步骤 3:实现**

```python
# src/blh/core/hooks.py
from collections import defaultdict
from typing import Callable

USER_PROMPT_SUBMIT = "UserPromptSubmit"
PRE_TOOL_USE = "PreToolUse"
POST_TOOL_USE = "PostToolUse"
STOP = "Stop"


class HookBus:
    def __init__(self):
        self._hooks: dict[str, list[Callable]] = defaultdict(list)

    def register(self, event: str, callback: Callable) -> None:
        self._hooks[event].append(callback)

    def trigger(self, event: str, *args, **kwargs) -> list:
        return [cb(*args, **kwargs) for cb in self._hooks.get(event, [])]

    def first_block(self, event: str, *args, **kwargs):
        for cb in self._hooks.get(event, []):
            result = cb(*args, **kwargs)
            if result is not None:
                return result
        return None
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/core/test_hooks.py -v
```

预期:4 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/core/hooks.py tests/core/test_hooks.py
git commit -m "feat(core): hook bus with first-block interception semantics"
```

---

### 任务 11:core/loop + core/harness

**文件:**
- 创建:`src/blh/core/loop.py`
- 创建:`src/blh/core/harness.py`
- 测试:`tests/core/test_loop.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/core/test_loop.py
import json

from blh.core.config import Config
from blh.core.harness import Harness
from blh.core.hooks import HookBus
from blh.core.loop import last_assistant_text
from blh.tools.registry import Tool, ToolRegistry


class MockProvider:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        if not self.scripted:
            raise AssertionError("MockProvider exhausted")
        return self.scripted.pop(0)


def tool_call_msg(call_id, name, args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def text_msg(text):
    return {"role": "assistant", "content": text, "tool_calls": None}


def make_harness(scripted, tools=None, hooks=None):
    cfg = Config(api_key="k", base_url=None, model="m", workdir=".")
    reg = ToolRegistry()
    for t in (tools or []):
        reg.register(t)
    return Harness(cfg, MockProvider(scripted), reg, hooks or HookBus())


def test_loop_stops_on_plain_text():
    h = make_harness([text_msg("done")])
    messages = h.new_session()
    h.run_turn(messages, "hi")
    assert last_assistant_text(messages) == "done"
    assert h.provider.calls == 1


def test_loop_dispatches_tool_then_stops():
    h = make_harness(
        [tool_call_msg("c1", "echo", {"text": "hello"}), text_msg("finished")],
        tools=[Tool("echo", "", {"type": "object",
                                 "properties": {"text": {"type": "string"}}},
                    handler=lambda text: text)],
    )
    messages = h.new_session()
    h.run_turn(messages, "go")
    tool_results = [m for m in messages if m["role"] == "tool"]
    assert tool_results[0]["tool_call_id"] == "c1"
    assert tool_results[0]["content"] == "hello"
    assert last_assistant_text(messages) == "finished"


def test_pre_tool_use_hook_blocks_dispatch():
    hooks = HookBus()
    hooks.register("PreToolUse", lambda e: "denied: no")
    h = make_harness(
        [tool_call_msg("c1", "echo", {"text": "x"}), text_msg("ok")],
        tools=[Tool("echo", "", {}, handler=lambda: "SHOULD NOT RUN")],
        hooks=hooks,
    )
    messages = h.new_session()
    h.run_turn(messages, "go")
    tool_results = [m for m in messages if m["role"] == "tool"]
    assert tool_results[0]["content"] == "denied: no"


def test_new_session_starts_with_system_message():
    h = make_harness([])
    messages = h.new_session()
    assert messages[0]["role"] == "system"
    assert "blh" in messages[0]["content"]
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/core/test_loop.py -v
```

预期:FAIL,`ModuleNotFoundError`。

- [ ] **步骤 3:实现**

```python
# src/blh/core/loop.py
import json

from .hooks import POST_TOOL_USE, PRE_TOOL_USE


def agent_loop(harness, messages: list[dict]) -> None:
    while True:
        assistant = harness.provider.chat(messages, harness.tools.schemas())
        messages.append(assistant)

        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            return

        for call in tool_calls:
            name = call["function"]["name"]
            arguments = call["function"].get("arguments") or "{}"
            event = {"name": name, "input": _parse_args(arguments), "id": call["id"]}

            blocked = harness.hooks.first_block(PRE_TOOL_USE, event)
            if blocked is not None:
                result = blocked
            else:
                result = harness.tools.dispatch(name, arguments)
                harness.hooks.trigger(POST_TOOL_USE, event, result)

            messages.append({"role": "tool",
                             "tool_call_id": call["id"],
                             "content": result})


def last_assistant_text(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg["role"] == "assistant" and msg.get("content"):
            return msg["content"]
    return ""


def _parse_args(arguments: str) -> dict:
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
```

```python
# src/blh/core/harness.py
from .config import Config
from .hooks import STOP, USER_PROMPT_SUBMIT, HookBus
from .loop import agent_loop


class Harness:
    def __init__(self, config: Config, provider, tools, hooks: HookBus):
        self.config = config
        self.provider = provider
        self.tools = tools
        self.hooks = hooks

    def system_prompt(self) -> str:
        return (
            f"You are blh, a coding agent. Workdir: {self.config.workdir}. "
            "Use the provided tools to act on the user's behalf. "
            "When the task is complete, summarize what you did."
        )

    def new_session(self) -> list[dict]:
        return [{"role": "system", "content": self.system_prompt()}]

    def run_turn(self, messages: list[dict], user_text: str) -> None:
        self.hooks.trigger(USER_PROMPT_SUBMIT, user_text)
        messages.append({"role": "user", "content": user_text})
        agent_loop(self, messages)
        self.hooks.trigger(STOP, messages)
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/core/test_loop.py -v
```

预期:4 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/core/loop.py src/blh/core/harness.py tests/core/test_loop.py
git commit -m "feat(core): agent loop with tool dispatch and harness orchestration"
```

---

### 任务 12:cli/main + cli/repl

**文件:**
- 创建:`src/blh/cli/main.py`
- 创建:`src/blh/cli/repl.py`
- 测试:`tests/cli/test_repl.py`

- [ ] **步骤 1:编写失败测试**

```python
# tests/cli/test_repl.py
from blh.cli.repl import repl
from blh.core.config import Config
from blh.core.harness import Harness
from blh.core.hooks import HookBus
from blh.tools.registry import ToolRegistry


class MockProvider:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools):
        self.calls += 1
        return {"role": "assistant",
                "content": f"reply-{self.calls}",
                "tool_calls": None}


def make_harness():
    cfg = Config(api_key="k", base_url=None, model="m", workdir=".")
    return Harness(cfg, MockProvider(), ToolRegistry(), HookBus())


def test_repl_runs_turns_until_exit(monkeypatch, capsys):
    inputs = iter(["hello", "", "again", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    repl(make_harness())

    out = capsys.readouterr().out
    assert "reply-1" in out
    assert "reply-2" in out


def test_repl_eof_exits_cleanly(monkeypatch, capsys):
    def raise_eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    repl(make_harness())  # 不抛异常即通过
```

- [ ] **步骤 2:运行测试验证失败**

```bash
pytest tests/cli/test_repl.py -v
```

预期:FAIL,`ModuleNotFoundError`。

- [ ] **步骤 3:实现**

```python
# src/blh/cli/repl.py
from ..core.loop import last_assistant_text


def repl(harness) -> None:
    messages = harness.new_session()
    print("blh — type 'exit' to quit")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text in ("exit", "quit"):
            break
        harness.run_turn(messages, text)
        reply = last_assistant_text(messages)
        if reply:
            print(reply)
```

```python
# src/blh/cli/main.py
import argparse

from ..core.config import load_config
from ..core.harness import Harness
from ..core.hooks import PRE_TOOL_USE, HookBus
from ..core.loop import last_assistant_text
from ..providers.openai import OpenAIProvider
from ..security.approval import make_permission_hook
from ..security.rules import DEFAULT_RULES
from ..tools import register_builtin_tools
from ..tools.registry import ToolRegistry
from .repl import repl


def build_harness(workdir: str | None = None) -> Harness:
    config = load_config(workdir)
    harness = Harness(config, OpenAIProvider(config), ToolRegistry(), HookBus())
    register_builtin_tools(harness.tools, config)
    harness.hooks.register(
        PRE_TOOL_USE, make_permission_hook(DEFAULT_RULES, config.workdir))
    return harness


def main() -> None:
    parser = argparse.ArgumentParser(prog="blh")
    parser.add_argument("-p", "--print", dest="prompt",
                        help="run a single prompt and print the reply")
    args = parser.parse_args()

    harness = build_harness()
    if args.prompt:
        messages = harness.new_session()
        harness.run_turn(messages, args.prompt)
        print(last_assistant_text(messages))
    else:
        repl(harness)


if __name__ == "__main__":
    main()
```

- [ ] **步骤 4:运行测试验证通过**

```bash
pytest tests/cli/test_repl.py -v
```

预期:2 passed。

- [ ] **步骤 5:Commit**

```bash
git add src/blh/cli tests/cli
git commit -m "feat(cli): REPL and one-shot -p entry point wiring full harness"
```

---

### 任务 13:端到端集成测试 + 全量验证

**文件:**
- 创建:`tests/test_integration.py`

- [ ] **步骤 1:编写端到端测试**

```python
# tests/test_integration.py
import json

from blh.core.config import Config
from blh.core.harness import Harness
from blh.core.hooks import PRE_TOOL_USE, HookBus
from blh.core.loop import last_assistant_text
from blh.security.approval import make_permission_hook
from blh.security.rules import DEFAULT_RULES
from blh.tools import register_builtin_tools
from blh.tools.registry import ToolRegistry


class MockProvider:
    def __init__(self, scripted):
        self.scripted = list(scripted)

    def chat(self, messages, tools):
        return self.scripted.pop(0)


def tool_call_msg(call_id, name, args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def text_msg(text):
    return {"role": "assistant", "content": text, "tool_calls": None}


def test_agent_writes_and_reads_file(tmp_path):
    """完整闭环:模型要求写文件 → 权限放行(自动 y)→ 读回 → 文本回复。"""
    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    hooks = HookBus()
    hooks.register(PRE_TOOL_USE,
                   make_permission_hook(DEFAULT_RULES, str(tmp_path),
                                        ask_fn=lambda prompt: "y"))
    tools = ToolRegistry()
    register_builtin_tools(tools, cfg)
    provider = MockProvider([
        tool_call_msg("c1", "write_file", {"path": "hello.txt", "content": "world"}),
        tool_call_msg("c2", "read_file", {"path": "hello.txt"}),
        text_msg("file created with content: world"),
    ])
    harness = Harness(cfg, provider, tools, hooks)

    messages = harness.new_session()
    harness.run_turn(messages, "create hello.txt containing 'world'")

    assert (tmp_path / "hello.txt").read_text() == "world"
    tool_results = [m for m in messages if m["role"] == "tool"]
    assert len(tool_results) == 2
    assert "world" in tool_results[1]["content"]
    assert last_assistant_text(messages) == "file created with content: world"


def test_agent_denied_by_permission(tmp_path):
    """bash 走 ask,用户拒绝 → 模型收到拒绝原因。"""
    cfg = Config(api_key="k", base_url=None, model="m", workdir=str(tmp_path))
    hooks = HookBus()
    hooks.register(PRE_TOOL_USE,
                   make_permission_hook(DEFAULT_RULES, str(tmp_path),
                                        ask_fn=lambda prompt: "n"))
    tools = ToolRegistry()
    register_builtin_tools(tools, cfg)
    provider = MockProvider([
        tool_call_msg("c1", "bash", {"command": "echo hi"}),
        text_msg("understood, command was denied"),
    ])
    harness = Harness(cfg, provider, tools, hooks)

    messages = harness.new_session()
    harness.run_turn(messages, "run echo hi")

    tool_results = [m for m in messages if m["role"] == "tool"]
    assert tool_results[0]["content"] == "denied by user"
```

- [ ] **步骤 2:运行测试验证通过**

```bash
pytest tests/test_integration.py -v
```

预期:2 passed。

- [ ] **步骤 3:全量验证 + lint**

```bash
pytest -v
ruff check src tests
```

预期:全部 passed(共 40+ 用例);ruff 无错误(如有自动修复项,`ruff check --fix` 后一并提交)。

- [ ] **步骤 4:真实 API 冒烟(可选,live 标记)**

```python
# tests/test_live.py
import os

import pytest

from blh.cli.main import build_harness
from blh.core.loop import last_assistant_text


@pytest.mark.live
def test_live_single_turn():
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("no API key")
    harness = build_harness()
    messages = harness.new_session()
    harness.run_turn(messages, "Reply with exactly: pong")
    assert "pong" in last_assistant_text(messages).lower()
```

```bash
pytest tests/test_live.py -v -m live   # 需要真实 OPENAI_API_KEY/OPENAI_BASE_URL/BLH_MODEL
```

- [ ] **步骤 5:Commit**

```bash
git add tests/test_integration.py tests/test_live.py
git commit -m "test: end-to-end integration tests with MockProvider and live smoke test"
```

---

## M0 验收清单(对照设计文档 7.1)

- [ ] `pip install -e ".[dev]"` 后 `blh` 命令可用
- [ ] REPL 与 `-p` 一次性模式均能对话
- [ ] 5 个内置工具(bash/read_file/write_file/edit_file/glob)经 OpenAI tool_calls 协议可调用
- [ ] 权限规则生效:默认 bash 询问、文件读写放行、`git push --force` 拒绝
- [ ] 权限以 `PreToolUse` hook 实现,非 dispatch 硬编码
- [ ] 429/5xx 自动重试
- [ ] `pytest` 全绿,`ruff check` 无错误

## 后续里程碑

- M1 计划:`compaction` / `planning` / `memory`(来源 s08/s05/s10/s09)
- M2 计划:`jobs`(来源 s11/s12)
- M3 计划:`agents`(来源 s06/s13)
- M4 计划:`extensions`(来源 s07/s14)
- M5 计划:`workflow` / `goals`(来源 s16/s17)
- M6 计划:配置体系、错误恢复完善、README、PyPI 发布
