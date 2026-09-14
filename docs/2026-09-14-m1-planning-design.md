# blh-claude-code M1.2:计划与追踪(planning) 设计

- **日期**:2026-09-14
- **状态**:设计已批准,待编写实现计划
- **来源**:learn-claude-code s05(todo_write)、s10(task system)
- **整体设计**:`../2026-09-13-blh-claude-code-design.md`(§4.1 将 s05/s10 归并为 `planning` 包)

---

## 1. 目标

新增 `blh.planning` 包,提供两类规划能力:

1. **todo 清单**(s05)——当前任务的短期执行清单,进程内内存态,带"连续三轮未更新即提醒"的 reminder。
2. **任务图**(s10)——跨会话可恢复的持久化任务系统,`.tasks/{id}.json` 落盘,支持 `blocked_by` 依赖与 owner 认领。

两者并存、互不共享状态:todo 是"此刻怎么一步步做",任务图是"这个大目标拆成哪些可认领、可追踪、可恢复的任务"。

## 2. 范围(7 个工具)

| 工具 | 来源 | 说明 |
|---|---|---|
| `todo_write` | s05 | 整表替换式更新内存清单(校验后渲染返回) |
| `create_task` | s10 | 创建任务节点,返回运行时生成的 ID |
| `update_task` | s10 | 用 create_task 返回的 ID 添加依赖边 |
| `list_tasks` | s10 | 一行摘要列出所有任务 |
| `get_task` | s10 | 返回单条任务完整 JSON |
| `claim_task` | s10 | 认领无依赖未完成的任务(pending → in_progress) |
| `complete_task` | s10 | 完成任务并解锁下游(in_progress → completed) |

## 3. 包结构

```
src/blh/planning/
  __init__.py   # 空
  todo.py       # TodoManager:items 校验/更新/渲染 + reminder 计数
  tasks.py      # Task dataclass + TaskStore:持久化 + 依赖 + 状态机
  tools.py      # register_planning_tools(registry, todo_manager, task_store)
```

- `todo.py` 不依赖 `tasks.py`;`tools.py` 依赖两者,只做"模型消息字符串渲染"。
- `tasks.py` 保持纯数据层(TaskStore 返回 `Task` / `list[Task]`);面向模型的字符串渲染(`Created ...`、`[ ] task_xxx: ...`)放 `tools.py`。

## 4. 状态归属(无全局状态)

- `TodoManager` 实例挂到 `Harness.todo_manager`(loop 层注入 reminder 需要访问)。
- `TaskStore` 实例由 `build_harness` 创建(`workdir / ".tasks"`),通过闭包注册进工具,不暴露到 Harness。

`Harness.__init__` 增加可选第 6 参 `todo_manager=None`(与既有第 5 参 `compactor=None` 同模式,默认 None 保持 M0/M1.1 行为不变)。

## 5. loop 集成(仅 reminder 一处)

- `TodoManager` 内部维护 `rounds_since_todo` 计数,方法 `note_round(used_todo: bool) -> str | None`。
- `agent_loop` 在每轮工具调用循环中跟踪 `used_todo`(本批是否含 `todo_write`),循环后调用 `note_round`;连续 3 轮未用且当前末尾是 `role=tool` 消息时,把 `<reminder>Update your todos.</reminder>` 追加到该消息 content 末尾。

OpenAI 协议下 reminder 无对应 `tool_call_id`,不能作为独立 `role=tool` 消息;追加到本批最后一条工具结果 content 是代价最小的注入点。纯文本轮(无 tool_calls)不计数,与教程一致。

## 6. 命名决策

统一 snake_case,放弃教程的 camelCase,与项目既有工具参数(`old_text`/`new_text` 等)及持久化字段保持一致:

| 教程(s10) | 本产品 |
|---|---|
| `addBlockedBy` | `add_blocked_by` |
| `blockedBy` | `blocked_by` |
| `task_id` | `task_id`(不变) |

## 7. 其余决策

- **system_prompt**:在 `Harness.system_prompt` 追加一行规划引导("Before starting a multi-step task, plan it with todo_write or create_task ..."),与既有 compaction 引导硬编码方式一致;不引入系统片段注册机制(YAGNI,避免超范围)。
- **`.gitignore`**:追加 `.tasks/`。
- **owner**:工具签名不暴露(单智能体,内部固定 `"agent"`);`Task` 保留 `owner` 字段为 M3 多智能体预留。`TaskStore.claim/complete` 保留 `owner="agent"` 默认参。
- **错误处理**:数据层错误(无效 ID、任务不存在、依赖不存在、环检测)抛 `ValueError`/`FileNotFoundError`,由 `ToolRegistry.dispatch` 统一转 `error: tool '{name}' failed: ...`;业务拒绝(状态不对、被依赖阻塞、非本人任务)返回普通字符串(非 error)。
- **持久化**:`TaskStore.create` 用排他写 `open("x")` 分配 `task_{8位hex}` ID;`_path` 用正则 `^task_[0-9a-f]{8}$` 校验 ID,天然防路径穿越。

## 8. 测试

- `tests/planning/test_todo.py`:TodoManager 校验/渲染/reminder 计数。
- `tests/planning/test_tasks.py`:TaskStore CRUD、依赖、环检测、状态机。
- `tests/planning/test_tools.py`:7 个工具 schema 与 handler 渲染。
- `tests/core/test_loop.py`:追加 reminder 注入集成测试(更新 `make_harness` 支持 `todo_manager`)。
- `tests/cli/test_main.py`:追加 `build_harness` 装配 planning 断言。
