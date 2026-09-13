# blh-claude-code 整合设计方案

- **日期**:2026-09-13
- **状态**:设计已批准,待实施
- **来源项目**:[learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)(s01-s17,17 章渐进式 agent harness 教程)

---

## 1. 背景与目标

将 learn-claude-code 教程中 s01-s17 共 17 个渐进式机制(每章一个独立 `code.py`,合计约 1.2 万行)整合为一个**可实际使用的 Agent CLI 产品**,命令名 `blh`。

教程代码的特征:s01-s14 每章机制独立自包含;s15 已将 s01-s14 机制集成进一个 3291 行的单体文件;s16(工作流运行时)通过 `install_workflow_tool(host)` 插件化挂载 s15;s17(目标循环)以外层 `GoalController` 包裹 session。教学代码存在全局状态、模块级单例、基于 Anthropic SDK 等问题,不可直接作为产品发布。

## 2. 已确认决策

| 决策点 | 结论 |
|---|---|
| 目标产物 | 可实际使用的 Agent CLI 产品 |
| 技术栈 | Python 3.11+(沿用教程栈;运行时核心依赖为 openai Python SDK,开发依赖 pytest / ruff) |
| 模型接口 | 仅 OpenAI 兼容接口(GLM / DeepSeek / MiniMax / Kimi / OpenAI 等均可接入) |
| 机制范围 | 全量 17 机制一次到位 |
| 仓库定位 | 纯产品仓库,不迁移教学资产(三语 README / SVG 图 / web 平台) |
| 整合路径 | 方案 C:核心骨架重写 + s15 已验证机制逐模块移植 + s16/s17 改造为插件 |
| 命令名 / 包名 | CLI 命令 `blh`,Python 包 `blh`,PyPI 发行名 `blh-claude-code` |

## 3. 整体架构

四层结构,每层只依赖下层:

```
┌─────────────────────────────────────────────┐
│  CLI 层      REPL / 一次性 -p / 子命令       │
├─────────────────────────────────────────────┤
│  Harness 核心  AgentLoop + 管线编排          │
│   (hooks → permission → dispatch → result)  │
├─────────────────────────────────────────────┤
│  功能域      按产品功能域划分的 10 个包      │
├─────────────────────────────────────────────┤
│  基础层      providers / 工具注册表 /        │
│              hook 总线 / 配置 / 持久化       │
└─────────────────────────────────────────────┘
```

**核心设计原则**:

1. **注册协议接入**:各功能域向核心声明"提供的工具、监听的 hook 事件、系统提示词片段",核心不知道功能域的存在——s04/s07/s14 思想的自我应用。
2. **显式 Harness 类**:持有 config、provider、hook bus、tool registry、session 状态,替代教学代码的全局状态,可实例化多个。
3. **功能域间禁止直接 import**:跨域协作一律走 hook 事件或工具池。

## 4. 包结构

```
blh-claude-code/
  pyproject.toml              # src 布局,entry point: blh = blh.cli:main
  src/blh/
    cli/            # 命令入口、REPL、流式渲染、审批交互
    core/           # Harness、agent loop、session、hook 总线、
                    #   系统提示词装配、配置、错误恢复、JSON 持久化基础设施
    providers/      # OpenAI 兼容接入(tool_calls 协议、重试、token 估算)
    tools/          # 工具框架(注册表/schema/dispatch)
                    #   + 内置工具(bash/read/write/edit/glob)
    security/       # 权限规则引擎、审批管线、路径沙箱
    compaction/     # 上下文压缩管线(budget → snip → micro → summarize)
    memory/         # 长期记忆(selection / extraction / consolidation)
    planning/       # todo 清单 + 任务图(依赖/认领/磁盘持久化)
    jobs/           # 后台任务 + cron 调度 + 完成通知注入
    agents/         # subagent + 团队(消息总线/协议/worktree 绑定)
    extensions/     # skills 按需加载 + MCP 客户端
    workflow/       # 工作流运行时(脚本编排/journal 断点恢复)
    goals/          # 目标循环(独立评估器/停止决策)
  tests/            # pytest,镜像 src 结构
  docs/
```

### 4.1 教程章节 → 产品功能域映射

| 教学章节 | 产品包 | 归并理由 |
|---|---|---|
| s01 agent loop / s04 hooks | `core` | 主循环与扩展点是内核 |
| s02 tool use | `tools` | 工具框架 + 内置工具 |
| s03 permission | `security` | 独立安全域,所有工具调用经此 |
| s05 todo / s10 任务图 | `planning` | 都是"计划与追踪",后者是前者的持久化升级 |
| s06 subagent / s13 agent teams | `agents` | 都是多智能体,subagent 是一次性 teammate |
| s07 skill loading / s14 MCP | `extensions` | 都是"按需扩展能力池",一个内部一个外部 |
| s08 context compact | `compaction` | 会话内被迫腾空间,独立演进 |
| s09 memory | `memory` | 跨会话主动留存,与压缩生命周期不同 |
| s11 background / s12 cron | `jobs` | 都是"异步单元 + 完成通知注入 loop" |
| s16 workflow runtime | `workflow` | 固定编排运行时,独立语义 |
| s17 goal loop | `goals` | 停止决策控制器,独立语义 |
| s15 integrated harness | (无对应包) | 集成职责由 `core.Harness` 承担;`code.py` 作为各机制移植时的集成参考 |

### 4.2 命名决策

- `providers`:表达"模型接入抽象层"而非模型本身;当前仅 OpenAI 兼容实现。
- `compaction` 与 `memory` 拆分:压缩是**会话内被迫腾空间**(四步管线),记忆是**跨会话主动留存**,生命周期不同,各自独立演进。
- `security`:容纳规则引擎 + 审批管线 + 路径沙箱,边界比 permissions 更完整。
- `jobs`:后台任务与 cron 共享"异步单元 + 完成通知"模型;cron job 一词天然涵盖两者。
- `extensions`:skills(内部知识扩展)与 MCP(外部工具接入)本质相同——按需扩充 agent 能力池。
- 不设 `runtime`/`storage` 包:bash/文件执行细节收敛为 `tools` 内部实现;JSON 原子写/锁等持久化基础设施收敛在 `core`,避免两个"杂物间"包。

## 5. 核心数据流

单轮管线(由 `core.Harness` 驱动):

```
用户输入
  → UserPromptSubmit hooks          # 审计/注入(s04)
  → jobs 通知注入                    # cron 到点 prompt + 后台完成通知(s11/s12)
  → compaction 管线                  # 超阈值时: budget → snip → micro → summarize(s08)
  → 装配 system 消息                 # memory + skills + MCP 状态(s07/s09/s14)
  → providers.chat(messages, tools)
  → finish_reason == "tool_calls"?
      否 → Stop hooks → 返回文本
      是 → 逐 tool_call:
             PreToolUse hooks(权限挂载点,s03 以 hook 实现)
             → 拒绝: 追加 role=tool 拒绝结果
             → 放行: dispatch(内置工具 / MCP 工具 / 后台标记分流)
             → PostToolUse hooks(大输出警告/日志)
             → 追加 role=tool 结果
  → 下一轮
```

## 6. OpenAI 协议适配

教程全部基于 Anthropic SDK,需逐项改写:

| 主题 | 教程(Anthropic) | 产品(OpenAI 兼容) |
|---|---|---|
| 工具调用 | `content` 中 `tool_use` block | `message.tool_calls[]`,`arguments` 为 JSON 字符串需 parse |
| 工具结果 | `role=user` + `tool_result` block | `role=tool` + `tool_call_id` |
| 系统提示 | 请求级 `system` 参数 | `messages[0] role=system` |
| 停止判定 | `stop_reason == "tool_use"` | `finish_reason == "tool_calls"` |
| 上下文超长 | 明确的 prompt-too-long 错误 | 各兼容端错误格式不一 → 按状态码 400 + 错误体关键词启发式判定,触发反应式压缩 |
| 限流重试 | 429/529 | 429 + 5xx 指数退避(429 读 `Retry-After`) |
| token 统计 | `usage` 字段 | 优先读 `usage`;部分兼容端流式不返回 → 回退本地字符估算(压缩管线依赖此值) |

两个核心决策:

1. **内部消息表示直接用 OpenAI 格式**——只支持这一种协议,不引入中间表示层(YAGNI)。压缩、持久化、transcript 都直接操作该格式。
2. **权限不硬编码在 dispatch 里,作为 `PreToolUse` hook 实现**(沿用 s15 设计)——审批、日志、审计共用同一挂载点;MCP 工具默认"只读白名单放行,其余询问";仅前台用户轮次可交互审批,异步轮次(cron/后台/团队)拒绝即失败,不抢 stdin。

## 7. 里程碑

全量 17 机制一次交付,实施按依赖顺序推进,**每个里程碑结束都保持可运行**。

| 里程碑 | 内容 | 移植来源 | 验收标准 |
|---|---|---|---|
| **M0 骨架与最小闭环** | 打包骨架、`providers`、`core`(loop/Harness/hook 总线)、`tools` 框架 + 5 个基础工具、`security`、`cli`(REPL + `-p`) | s01/s02/s03/s04 + s15 工具部分 | 能对话、执行工具、权限审批生效 |
| **M1 上下文与规划** | `compaction` 四步管线 + 反应式压缩、`planning`(todo + 任务图)、`memory` | s08/s05/s10/s09 | 长对话自动压缩;任务可依赖/持久化;记忆可存取 |
| **M2 异步与调度** | `jobs`:后台任务 + 通知注入、cron | s11/s12 | 后台执行不阻塞;cron 到点注入 |
| **M3 多智能体** | `agents`:subagent、团队(消息总线/协议/worktree/原子认领) | s06/s13 | subagent 隔离返回;多 teammate 协同认领 |
| **M4 扩展能力** | `extensions`:skills 加载、MCP 客户端 | s07/s14 | load_skill 生效;接入真实 MCP server |
| **M5 编排与目标闭环** | `workflow`(journal 恢复)、`goals` | s16/s17 | 工作流断点恢复;评估器控制停止/续行 |
| **M6 打磨与发布** | 配置体系(文件 + env)、错误恢复完善、README、PyPI 发布 | — | `pipx install` 可用 |

## 8. 测试策略

- **单元测试**:每包独立测试,mock provider;`tests/` 镜像 `src/` 结构。
- **集成测试**:自研 `MockProvider`(脚本化返回预定 `tool_calls`)驱动完整 loop,不依赖真实 API——借鉴教程 s16 已有的 `MockAgentRunner` 模式。
- **移植复用**:教程 `tests/` 中可复用的用例(压缩配对、cron 解析、权限、任务系统等)改写适配新结构,不重写测试逻辑。
- **真实 API 冒烟**:少量用例标记 `@pytest.mark.live`,默认跳过,手动触发。
- **CI**:GitHub Actions 跑 lint(ruff)+ pytest。

## 9. 非目标(Out of Scope)

- 不迁移教程教学资产:17 章三语 README、SVG 图、`web/` 可视化平台。
- 不支持 Anthropic 原生协议、不支持除 OpenAI 兼容接口外的 provider。
- v1 不做:LSP 集成、IDE 插件、Web UI、多语言绑定。
- 不向后兼容教程的 `code.py` 脚本接口(新产品有自己的 CLI 契约)。
