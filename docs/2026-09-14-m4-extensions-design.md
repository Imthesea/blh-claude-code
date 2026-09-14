# blh-claude-code M4:扩展能力 设计文档

- **日期**:2026-09-14
- **状态**:已实施
- **来源**:learn-claude-code s07(skill loading) + s14(MCP)

---

## 1. 目标

新增 `blh.extensions` 包,提供两类"按需扩展能力池":

1. **skills**:启动时只注入技能目录(catalog),模型调用 `load_skill` 时才加载完整 `SKILL.md`。
2. **MCP**:连接外部 MCP server,发现其工具并纳入 agent loop,`mcp__{server}__{tool}` 命名。

设计文档 M4 验收:load_skill 生效;接入真实 MCP server。

## 2. 已确认决策

| 决策点 | 结论 |
|---|---|
| MCP 传输 | 真实 stdio 传输,自己实现 JSON-RPC over stdio,不引入 mcp SDK |
| MCP server 配置来源 | `connect_mcp(name, command, args)` 工具显式传入启动命令与参数 |
| skills 目录 | 固定 `workdir/skills`,每个技能一个子目录含 `SKILL.md` |
| MCP 工具命名 | `mcp__{safe_server}__{safe_tool}`(非法字符转 `_`) |
| MCP 权限 | host 决定,默认确认;只读描述不构成信任 |

## 3. 包结构

```
src/blh/extensions/
  __init__.py
  skills.py   # SkillLoader:frontmatter 解析、扫描、catalog、load
  mcp.py      # MCPClient(单连接)+ MCPRegistry(多连接)+ 命名归一化
  tools.py    # register_extension_tools:注册 load_skill / connect_mcp
```

## 4. SkillLoader

- `SkillLoader(skills_dir)` 扫描 `skills_dir/*/SKILL.md`,只接受真实子目录内文件(拒绝符号链接逃逸)。
- `parse_frontmatter(text) -> (metadata, body)`:解析开头 `---` 包裹的 YAML frontmatter;非法 YAML 视为空 metadata。
- 技能 `name` 取 frontmatter `name`,回退目录名;`description` 取 frontmatter `description`,回退 body 首行。
- 接口:`catalog() -> str`(逐行 `- name: description`)、`load(name) -> str`(返回完整 SKILL.md 或报错列出可用名)。

## 5. MCP 客户端

### 5.1 stdio 传输(NDJSON JSON-RPC)

- spawn 子进程 `Popen([command, *args], stdin/stdout=PIPE, stderr=PIPE, text=True, encoding="utf-8")`。
- 每条消息 = 一行 JSON(`json.dumps` + `\n`),不包含内嵌换行;stderr 仅日志,不解析。
- 客户端写 request/notification 到 stdin,读 stdout 逐行 `json.loads`,按 JSON-RPC `id` 匹配响应;无 `id` 的通知跳过。
- 读响应带超时,超时返回错误字符串而非挂死。

### 5.2 生命周期与调用

1. `initialize` 请求(`protocolVersion="2024-11-05"`,`capabilities={}`,`clientInfo={name:"blh",version:"0.1.0"}`)。
2. 收到响应后发 `notifications/initialized` 通知。
3. `tools/list` 返回 `result.tools`(含 `name`/`description`/`inputSchema`)。
4. `tools/call`(`params={name, arguments}`)返回 `result.content`(拼接 `text` 段)与 `isError`。
5. 关闭:关 stdin → 等退出 → 超时 `terminate` → 再 `kill`。

### 5.3 MCPClient 与 MCPRegistry

- `MCPClient`:单连接,持有 `name`/`process`/`_next_id`,暴露 `start`/`list_tools`/`call_tool`/`close`。
- `MCPRegistry`:多连接,持有 `ToolRegistry` 引用与 `workdir`,暴露:
  - `connect(name, command, args=None) -> str`:校验重名 → spawn+initialize+list_tools → 逐个注册 `mcp__server__tool` 进 ToolRegistry。
  - `system_prompt_section() -> str`:返回已连接 server 摘要。

### 5.4 命名归一化

- `normalize_mcp_name(name)`:将 `[^a-zA-Z0-9_-]` 替换为 `_`,空结果报错。
- 前缀 `mcp__{safe_server}__{safe_tool}`;超过 64 字符报错;归一化后碰撞报错(记录 origin)。

## 6. 权限接入

复用现有 `security` 规则引擎,在 `DEFAULT_RULES` 的 `("*","*","allow")` 之前插入两条兜底:

- `PermissionRule("mcp__*", "*", "ask")` — 外部工具默认确认。
- `PermissionRule("connect_mcp", "*", "ask")` — 启动子进程默认确认。

用户可在配置中放置更靠前的显式 `allow` 规则放行特定 MCP 工具;非主线程轮次无法确认即拒绝(沿用现有语义)。

## 7. Harness 集成

- `Harness` 新增 `extensions` 字段(默认 None),`system_prompt()` 追加技能目录与已连接 MCP server 摘要。
- `build_harness` 构造 `SkillLoader(workdir/skills)`、`MCPRegistry(tools, workdir)` 并 `register_extension_tools`,传给 Harness。
- MCP 工具经 `connect_mcp` 动态注册进同一个 `ToolRegistry`,下一轮 `schemas()` 自动包含,无需改动 loop。

## 8. 测试策略

- 假 MCP server:用 `sys.executable -m` 启动一个极简 stdio server(实现 initialize/tools_list/tools_call),测试真实进程往返。
- `SkillLoader`/`MCPRegistry`/命名归一化/权限规则单测;`register_extension_tools` 单测;`build_harness` 集成测试。
