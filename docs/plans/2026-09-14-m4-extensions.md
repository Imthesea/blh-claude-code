# blh-claude-code M4:扩展能力 实现计划

- **日期**:2026-09-14
- **依据**:`docs/2026-09-14-m4-extensions-design.md`
- **方法**:TDD,每个任务「失败测试 → 实现 → 验证 → commit」

## 任务总览

| # | 任务 | 产物 |
|---|---|---|
| 1 | SkillLoader | `extensions/skills.py` |
| 2 | MCP stdio JSON-RPC 传输 | `extensions/mcp.py`(MCPClient) |
| 3 | MCPRegistry + 命名归一化 + 注册 | `extensions/mcp.py`(MCPRegistry) |
| 4 | MCP 权限默认 ask | `security/rules.py` |
| 5 | register_extension_tools | `extensions/tools.py` |
| 6 | Harness 集成 | `core/harness.py` |
| 7 | main 装配 | `cli/main.py` |
| 8 | 收尾验证 | 全量测试 + ruff |

---

## 任务 1:SkillLoader

### 1.1 失败测试 `tests/extensions/test_skills.py`

```python
import pytest

from blh.extensions.skills import SkillLoader


def _write_skill(root, name, content):
    d = root / name
    d.mkdir()
    (d / "SKILL.md").write_text(content, encoding="utf-8")
    return d


def test_parse_frontmatter_basic():
    meta, body = SkillLoader.parse_frontmatter(
        "---\nname: code-review\ndescription: 审查代码\n---\n正文")
    assert meta == {"name": "code-review", "description": "审查代码"}
    assert body == "正文"


def test_parse_frontmatter_missing():
    meta, body = SkillLoader.parse_frontmatter("无 frontmatter")
    assert meta == {}
    assert body == "无 frontmatter"


def test_scan_catalog_and_load(tmp_path):
    _write_skill(tmp_path, "alpha", "---\nname: a\ndescription: 第一个\n---\nA body")
    _write_skill(tmp_path, "beta", "---\nname: b\ndescription: 第二个\n---\nB body")
    loader = SkillLoader(tmp_path)
    assert "a: 第一个" in loader.catalog()
    assert "b: 第二个" in loader.catalog()
    assert loader.load("a") == "---\nname: a\ndescription: 第一个\n---\nA body"


def test_load_unknown_lists_available(tmp_path):
    _write_skill(tmp_path, "alpha", "---\nname: a\ndescription: 第一个\n---\n")
    loader = SkillLoader(tmp_path)
    assert "Unknown skill 'nope'" in loader.load("nope")
    assert "a" in loader.load("nope")
```

### 1.2 实现 `src/blh/extensions/skills.py`

```python
"""技能按需加载:启动注入目录,load_skill 才读完整 SKILL.md。"""

from pathlib import Path

import yaml


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, dict[str, str]] = {}
        self.scan()

    @staticmethod
    def parse_frontmatter(text: str) -> tuple[dict, str]:
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != "---":
            return {}, text
        closing = next((i for i, line in enumerate(lines[1:], start=1)
                        if line.rstrip("\r\n") == "---"), None)
        if closing is None:
            return {}, text
        frontmatter = "".join(lines[1:closing])
        body = "".join(lines[closing + 1:]).strip()
        try:
            meta = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError:
            meta = {}
        return (meta if isinstance(meta, dict) else {}), body

    def scan(self):
        self.skills.clear()
        if not self.skills_dir.exists():
            return
        root = self.skills_dir.resolve()
        for manifest in sorted(self.skills_dir.glob("*/SKILL.md")):
            if not manifest.is_file() or not manifest.resolve().is_relative_to(root):
                continue
            content = manifest.read_text(encoding="utf-8")
            meta, body = self.parse_frontmatter(content)
            name = (meta.get("name") or "").strip() or manifest.parent.name
            description = (meta.get("description") or "").strip() or body.split("\n", 1)[0]
            description = " ".join(str(description).lstrip("# ").split())
            self.skills[name] = {"name": name, "description": description,
                                 "content": content}

    def catalog(self) -> str:
        if not self.skills:
            return "(no skills found)"
        return "\n".join(f"- {s['name']}: {s['description']}"
                         for s in self.skills.values())

    def load(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill:
            return skill["content"]
        available = ", ".join(self.skills) or "none"
        return f"Error: Unknown skill '{name}'. Available: {available}"
```

### 1.3 验证

```powershell
uv run pytest tests/extensions/test_skills.py -q
```

### 1.4 commit

```
feat(extensions): add SkillLoader for on-demand skill loading
```

---

## 任务 2:MCP stdio JSON-RPC 传输

### 2.1 失败测试 `tests/extensions/test_mcp.py`(底层部分)

假 server 用 `sys.executable -c SERVER_CODE` 启动,实现 `initialize`/`tools/list`/`tools/call` 的 NDJSON server。

```python
import sys

import pytest

from blh.extensions.mcp import MCPClient

SERVER_CODE = r'''
import json, sys

def reply(req, result):
    json.dump({"jsonrpc": "2.0", "id": req["id"], "result": result}, sys.stdout)
    sys.stdout.write("\n"); sys.stdout.flush()

def send_notification(method):
    json.dump({"jsonrpc": "2.0", "method": method}, sys.stdout)
    sys.stdout.write("\n"); sys.stdout.flush()

TOOLS = [
    {"name": "search", "description": "Search docs.",
     "inputSchema": {"type": "object",
                     "properties": {"query": {"type": "string"}},
                     "required": ["query"]}},
]
for line in sys.stdin:
    req = json.loads(line)
    method = req.get("method")
    if method == "initialize":
        reply(req, {"protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake", "version": "1.0"}})
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        reply(req, {"tools": TOOLS})
    elif method == "tools/call":
        params = req["params"]
        if params["name"] != "search":
            reply(req, {"content": [{"type": "text",
                                     "text": f"unknown tool: {params['name']}"}],
                        "isError": True})
        else:
            args = params["arguments"]
            reply(req, {"content": [{"type": "text",
                                     "text": f"searched {args.get('query')}"}],
                        "isError": False})
    else:
        reply(req, {"content": [], "isError": False})
'''


def _start_client():
    return MCPClient("fake", sys.executable, ["-c", SERVER_CODE])


def test_initialize_and_list_tools():
    client = _start_client()
    try:
        client.start()
        tools = client.list_tools()
        assert [t["name"] for t in tools] == ["search"]
    finally:
        client.close()


def test_call_tool():
    client = _start_client()
    try:
        client.start()
        assert client.call_tool("search", {"query": "x"}) == "searched x"
    finally:
        client.close()


def test_call_unknown_tool():
    client = _start_client()
    try:
        client.start()
        assert "unknown tool" in client.call_tool("nope", {})
    finally:
        client.close()
```

### 2.2 实现 `src/blh/extensions/mcp.py`(MCPClient 部分)

```python
"""MCP 客户端:JSON-RPC over stdio 传输,连接真实 MCP server。"""

import json
import subprocess
import time

PROTOCOL_VERSION = "2024-11-05"


class MCPClient:
    def __init__(self, name, command, args=None, timeout=30):
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.timeout = timeout
        self.process = None
        self._next_id = 1

    def start(self):
        self.process = subprocess.Popen(
            [self.command, *self.args], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace")
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "blh", "version": "0.1.0"},
        })
        if "error" in result:
            raise RuntimeError(f"initialize failed: {result['error']}")
        self._notify("notifications/initialized")

    def list_tools(self):
        result = self._request("tools/list", {})
        if "error" in result:
            raise RuntimeError(f"tools/list failed: {result['error']}")
        return result.get("tools", [])

    def call_tool(self, tool_name, arguments):
        result = self._request("tools/call",
                               {"name": tool_name, "arguments": arguments})
        if "error" in result:
            return f"MCP error: {result['error']}"
        content = result.get("content", [])
        text = "\n".join(c.get("text", "") for c in content
                         if isinstance(c, dict) and c.get("type") == "text")
        return text or "(empty result)"

    def close(self):
        if self.process is None:
            return
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None

    # ---- 帧编解码 ----
    def _request(self, method, params):
        rid = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": rid, "method": method,
                    "params": params})
        return self._read_response(rid)

    def _notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def _send(self, msg):
        self.process.stdin.write(json.dumps(msg) + "\n")
        self.process.stdin.flush()

    def _read_response(self, rid):
        deadline = time.time() + self.timeout
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError(f"MCP server '{self.name}' closed stdout")
            data = json.loads(line)
            if data.get("id") == rid:
                return data.get("result", {"error": data.get("error")})
            if time.time() > deadline:
                raise TimeoutError(f"MCP request timed out after {self.timeout}s")
```

> 注:`_read_response` 中通知消息(无 `id`)会被 `data.get("id") == rid` 自然跳过,继续读下一行。

### 2.3 验证

```powershell
uv run pytest tests/extensions/test_mcp.py -q
```

### 2.4 commit

```
feat(extensions): add MCP stdio JSON-RPC client
```

---

## 任务 3:MCPRegistry + 命名归一化 + 注册进 ToolRegistry

### 3.1 失败测试(追加到 `tests/extensions/test_mcp.py`)

```python
from blh.extensions.mcp import MCPRegistry, normalize_mcp_name
from blh.tools.registry import ToolRegistry


def test_normalize_mcp_name():
    assert normalize_mcp_name("docs.one/get") == "docs_one_get"


def test_normalize_mcp_name_empty_raises():
    with pytest.raises(ValueError):
        normalize_mcp_name("")


def test_connect_registers_prefixed_tools():
    registry = ToolRegistry()
    mcp = MCPRegistry(registry, ".")
    result = mcp.connect("fake", sys.executable, ["-c", SERVER_CODE])
    assert "fake" in result
    names = [s["function"]["name"] for s in registry.schemas()]
    assert "mcp__fake__search" in names


def test_connect_duplicate_returns_message():
    registry = ToolRegistry()
    mcp = MCPRegistry(registry, ".")
    mcp.connect("fake", sys.executable, ["-c", SERVER_CODE])
    assert "already connected" in mcp.connect("fake", sys.executable,
                                              ["-c", SERVER_CODE])


def test_system_prompt_section():
    registry = ToolRegistry()
    mcp = MCPRegistry(registry, ".")
    assert mcp.system_prompt_section() == ""
    mcp.connect("fake", sys.executable, ["-c", SERVER_CODE])
    assert "fake" in mcp.system_prompt_section()
```

> 注:第一版会因 `MCPRegistry` 不存在而 import 失败,属预期失败。

### 3.2 实现(追加到 `src/blh/extensions/mcp.py`)

```python
import re
from ..tools.registry import Tool

_DISALLOWED = re.compile(r"[^a-zA-Z0-9_-]")


def normalize_mcp_name(name: str) -> str:
    normalized = _DISALLOWED.sub("_", name)
    if not normalized:
        raise ValueError("MCP names cannot normalize to an empty string")
    return normalized


class MCPRegistry:
    def __init__(self, registry, workdir):
        self.registry = registry
        self.workdir = workdir
        self.clients: dict[str, MCPClient] = {}
        self._origins: dict[str, str] = {}

    def connect(self, name, command, args=None) -> str:
        if not name:
            return "Error: server name is required"
        if name in self.clients:
            return f"MCP server '{name}' already connected"
        safe_server = normalize_mcp_name(name)
        client = MCPClient(name, command, args)
        try:
            client.start()
            tools = client.list_tools()
        except Exception as exc:  # noqa: BLE001 - 连接失败返回给模型
            client.close()
            return f"Error: failed to connect MCP server '{name}': {exc}"
        registered = []
        for tool_def in tools:
            raw_name = tool_def.get("name", "")
            if not raw_name:
                continue
            safe_tool = normalize_mcp_name(raw_name)
            prefixed = f"mcp__{safe_server}__{safe_tool}"
            if len(prefixed) > 64:
                return f"Error: MCP tool name too long: {prefixed}"
            if prefixed in self._origins:
                return f"Error: MCP tool name collision: {prefixed}"
            schema = tool_def.get("inputSchema", {})
            self._origins[prefixed] = f"MCP tool '{name}/{raw_name}'"
            self.registry.register(Tool(
                name=prefixed,
                description=tool_def.get("description", ""),
                parameters=schema if isinstance(schema, dict) else
                {"type": "object", "properties": {}},
                handler=self._make_handler(client, raw_name),
            ))
            registered.append(prefixed)
        self.clients[name] = client
        names = ", ".join(registered) or "none"
        return (f"Connected to MCP server '{name}'. "
                f"Discovered {len(registered)} tools: {names}")

    def system_prompt_section(self) -> str:
        if not self.clients:
            return ""
        return "Connected MCP servers: " + ", ".join(self.clients)

    @staticmethod
    def _make_handler(client, raw_name):
        def handler(**kwargs):
            return client.call_tool(raw_name, kwargs)
        return handler
```

### 3.3 验证

```powershell
uv run pytest tests/extensions/test_mcp.py -q
```

### 3.4 commit

```
feat(extensions): add MCPRegistry with name normalization and tool registration
```

---

## 任务 4:MCP 权限默认 ask

### 4.1 失败测试(追加到 `tests/security/test_rules.py`)

```python
def test_mcp_tools_ask_by_default():
    from blh.security.rules import DEFAULT_RULES, match_rule
    assert match_rule(DEFAULT_RULES, "mcp__docs__search", "") == "ask"
    assert match_rule(DEFAULT_RULES, "connect_mcp", "") == "ask"
```

### 4.2 实现 `src/blh/security/rules.py`

`match_rule` 的 tool 字段改为 fnmatch 通配匹配(向后兼容,`"bash"`/`"*"` 行为不变):

```python
def match_rule(rules: list[PermissionRule], tool: str, target: str) -> str:
    for rule in rules:
        if rule.tool != "*" and not fnmatch.fnmatch(tool, rule.tool):
            continue
        if fnmatch.fnmatch(target, rule.pattern):
            return rule.action
    return "ask"
```

并在 `DEFAULT_RULES` 中,`PermissionRule("*", "*", "allow")` 之前插入:

```python
    PermissionRule("mcp__*", "*", "ask"),
    PermissionRule("connect_mcp", "*", "ask"),
```

### 4.3 验证

```powershell
uv run pytest tests/security/test_rules.py -q
```

### 4.4 commit

```
feat(security): default MCP tools and connect_mcp to ask
```

---

## 任务 5:register_extension_tools

### 5.1 失败测试 `tests/extensions/test_tools.py`

```python
from blh.extensions.skills import SkillLoader
from blh.extensions.mcp import MCPRegistry
from blh.extensions.tools import register_extension_tools
from blh.tools.registry import ToolRegistry


def test_registers_load_skill_and_connect_mcp(tmp_path):
    registry = ToolRegistry()
    skills = SkillLoader(tmp_path / "skills")
    mcp = MCPRegistry(registry, ".")
    register_extension_tools(registry, skills, mcp)
    names = [s["function"]["name"] for s in registry.schemas()]
    assert "load_skill" in names
    assert "connect_mcp" in names
```

### 5.2 实现 `src/blh/extensions/tools.py`

```python
"""extensions 工具注册:load_skill + connect_mcp。"""

from ..tools.registry import Tool, ToolRegistry


def register_extension_tools(registry: ToolRegistry, skills, mcp) -> None:
    registry.register(Tool(
        name="load_skill",
        description="Load the full SKILL.md content by skill name.",
        parameters={"type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"]},
        handler=skills.load,
    ))
    registry.register(Tool(
        name="connect_mcp",
        description="Connect to an MCP server and discover its tools.",
        parameters={"type": "object",
                    "properties": {"name": {"type": "string"},
                                   "command": {"type": "string"},
                                   "args": {"type": "array",
                                           "items": {"type": "string"}}},
                    "required": ["name", "command"]},
        handler=lambda name, command, args=None:
            mcp.connect(name, command, args),
    ))
```

### 5.3 验证

```powershell
uv run pytest tests/extensions/test_tools.py -q
```

### 5.4 commit

```
feat(extensions): register load_skill and connect_mcp tools
```

---

## 任务 6:Harness 集成

### 6.1 失败测试(追加到 `tests/core/test_loop.py`)

```python
def test_harness_system_prompt_includes_skill_catalog(tmp_path):
    from blh.extensions import Extensions
    from blh.extensions.skills import SkillLoader
    from blh.extensions.mcp import MCPRegistry
    (tmp_path / "skills" / "alpha").mkdir(parents=True)
    (tmp_path / "skills" / "alpha" / "SKILL.md").write_text(
        "---\nname: a\ndescription: 第一个\n---\nbody", encoding="utf-8")
    skills = SkillLoader(tmp_path / "skills")
    ext = Extensions(skills, MCPRegistry(ToolRegistry(), str(tmp_path)))
    harness = make_harness([], extensions=ext)
    assert "Skills available" in harness.system_prompt()
    assert "a: 第一个" in harness.system_prompt()
```

> `make_harness` 需先加 `extensions=None` 参数并透传(同任务 8 的做法)。

### 6.2 实现

**`src/blh/extensions/__init__.py`**

```python
"""扩展能力:skills 按需加载 + MCP 客户端。"""


class Extensions:
    def __init__(self, skills, mcp):
        self.skills = skills
        self.mcp = mcp

    def system_prompt_section(self) -> str:
        parts = []
        catalog = self.skills.catalog()
        if catalog != "(no skills found)":
            parts.append("Skills available:\n" + catalog)
        section = self.mcp.system_prompt_section()
        if section:
            parts.append(section)
        return "\n\n".join(parts)
```

**`src/blh/core/harness.py`**:`__init__` 加 `extensions=None`,赋值 `self.extensions`;`system_prompt()` 末尾拼接:

```python
    def system_prompt(self) -> str:
        base = ( ... 现有内容 ... )
        if self.extensions is None:
            return base
        section = self.extensions.system_prompt_section()
        return f"{base}\n\n{section}" if section else base
```

### 6.3 验证

```powershell
uv run pytest tests/core/test_loop.py -q
```

### 6.4 commit

```
feat(core): wire extensions into Harness system prompt
```

---

## 任务 7:main 装配

### 7.1 失败测试(追加到 `tests/cli/test_main.py`)

```python
def test_build_harness_wires_extensions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.extensions is not None
    names = [s["function"]["name"] for s in harness.tools.schemas()]
    assert "load_skill" in names
    assert "connect_mcp" in names
```

### 7.2 实现 `src/blh/cli/main.py`

```python
from ..extensions import Extensions
from ..extensions.mcp import MCPRegistry
from ..extensions.skills import SkillLoader
from ..extensions.tools import register_extension_tools
```

在 `register_agent_tools(...)` 之后:

```python
    skills = SkillLoader(wd / "skills")
    mcp = MCPRegistry(tools, config.workdir)
    register_extension_tools(tools, skills, mcp)
    extensions = Extensions(skills, mcp)
    return Harness(config, provider, tools, hooks, compactor, todo_manager,
                   memory, jobs, agents, extensions)
```

### 7.3 验证

```powershell
uv run pytest tests/cli/test_main.py -q
```

### 7.4 commit

```
feat(cli): assemble extensions in build_harness
```

---

## 任务 8:收尾验证

```powershell
uv run pytest -q
uv run ruff check src/blh tests
```

两项均通过后,更新 `docs/2026-09-14-m4-extensions-design.md` 状态为「已实施」,汇总 M4 完成。
