# blh-claude-code M3:多智能体(agents) 设计

- **日期**:2026-09-14
- **状态**:设计已批准,待编写实现计划
- **来源**:learn-claude-code s06(subagent)、s13(agent teams)
- **整体设计**:`../2026-09-13-blh-claude-code-design.md`(§4.1 将 s06/s13 归并为 `agents` 包,§7 里程碑 M3)

---

## 1. 目标

新增 `blh.agents` 包,提供两级委派能力,让 Agent 把工作拆出去、由队友分头完成:

1. **subagent(s06)**——`task` 工具:同步运行一段**全新 messages[]** 的嵌套 Agent Loop,只返回最终文本给父对话,中间工具调用不污染父上下文;子循环只有 5 个基础工具,没有 `task`,不可二次委派。
2. **团队(s13)**——`spawn_teammate`/`list_teammates`/`send_message`/`request_shutdown`/`request_plan`/`review_plan`/`create_worktree` 7 个 Lead 工具 + 持久队友线程 + MessageBus 文件收件箱 + 共享任务板原子认领 + 可选 worktree + 类型化关机/计划审批协议。

两者关系:subagent 是**一次性同步委派**(一次调用返回一次结果);队友是**持久执行单元**(WORK/IDLE 循环,跨任务保留上下文,与 Lead 双向协作)。共享的底层是"独立 messages + 完成结果回投 Lead 上下文"。

## 2. 范围

| 项 | 来源 | 说明 |
|---|---|---|
| `task` | s06 | 同步嵌套 loop,基础工具 + 权限 hook,最多 30 轮,返回最终文本 |
| `spawn_teammate` | s13 | 启动持久队友,可选 `task_id`/`require_plan` |
| `list_teammates` | s13 | 列出活跃队友与状态 |
| `send_message` | s13 | Lead 与队友互发消息 |
| `request_shutdown` | s13 | 类型化关机握手 |
| `request_plan` / `review_plan` | s13 | 类型化计划审批(审批前锁修改型工具) |
| `create_worktree` | s13 | Lead 专用,任务绑定独立 Git worktree |
| 队友工具 | s13 | `bash/read_file/write_file/edit_file/glob/send_message/submit_plan/list_tasks/claim_task/complete_task` |

非目标:`remove_worktree` 是宿主函数(不暴露为模型工具);不引入跨进程文件锁(见 §9)。

## 3. 包结构

```
src/blh/agents/
  __init__.py   # 空
  subagent.py   # SubagentRunner:provider + 基础工具 + hook bus,run_subagent 嵌套 loop
  bus.py        # MessageBus:.mailboxes/<name>.jsonl 线程安全文件收件箱
  worktree.py   # git worktree 纯操作:validate_name / resolve_path / branch / create / remove
  teammate.py   # TeammateRuntime:单队友 WORK/IDLE 循环 + 队友工具 + 收件箱处理
  team.py       # TeamRuntime:组合 bus/teammate/协议/assignment/plan gate + 线程生命周期
  tools.py      # register_agent_tools:task + 7 个 Lead 团队工具
```

- `subagent.py`/`bus.py`/`worktree.py` 互不依赖,各自独立可测。
- `team.py` 依赖 `bus.py`、`worktree.py`、`planning.tasks`(TaskStore);是状态与生命周期的唯一持有者。
- `teammate.py` **不 import** `team.py`,通过构造注入的回调(claim/complete/submit_plan/send/bus)协作,避免循环依赖。
- `tools.py` 只依赖 `subagent.py` 与 `team.py`,做模型消息字符串渲染。

## 4. 状态归属(无全局状态)

教程用模块级全局(`BUS`、`active_teammates`、`plan_gates`、`pending_requests`、`teammate_assignments`、`teammate_threads`),产品全部收敛为 `TeamRuntime` 的实例字段:

- `TeamRuntime` 持有:`TaskStore`、`MessageBus`、`agent_lock`、`workdir`、provider、`dict[str, TeammateRuntime]`(active teammates)、`dict[str, str]`(plan gates)、`dict[str, ProtocolState]`(pending requests)、`dict[str, dict]`(assignment registry)、`dict[str, threading.Thread]`(threads)。
- `TeamRuntime` 挂到 `Harness.agents`(新增可选第 9 参 `agents=None`,默认 None 保持 M0–M2 行为不变)。
- `SubagentRunner` 由 `build_harness` 创建(provider + config + hooks),通过 `register_agent_tools` 闭包注册 `task` 工具,不暴露到 Harness。

`Harness.__init__` 参数顺序:`config, provider, tools, hooks, compactor=None, todo_manager=None, memory=None, jobs=None, agents=None`。

## 5. 线程模型与锁

| 线程 | 来源 | 职责 |
|---|---|---|
| 主线程(REPL) | 既有 | 用户回合:`input` → `harness.run_turn`;`task` 同步嵌套 loop 也在此线程 |
| teammate(daemon,×N) | s13 | 每个队友独立 WORK/IDLE 循环,读写自己的 messages + 收件箱 + 任务板 |
| lead-inbox-processor(daemon) | s13 | 每 0.2s 检查 Lead 收件箱,拿到 `agent_lock` 后跑一轮 Lead 回合 |

- **共享 `agent_lock`**:用户回合、cron 回合(M2)、Lead 团队回合(M3)都会改写同一份 `messages`,必须互斥。`build_harness` 把 `JobsRuntime.agent_lock`(既有)作为同一把锁传给 `TeamRuntime`(必填参 `agent_lock`),两者共享;REPL 用户回合继续用 `with harness.jobs.agent_lock:` 包裹。无需改动 `JobsRuntime`。
- **Lead 回合**由 lead-inbox-processor 线程 `acquire(blocking=False)` 抢锁,抢不到跳过(等 agent 空闲);队友线程不碰 Lead 的 `messages`,只在收件箱投递事件。
- **队友线程随进程消失**;队友在 Agent 进程存活时才运行(与教程一致的运行边界)。`TeamRuntime.start()`/`stop()` 幂等,`stop()` 置 `Event` 并向所有活跃队友发送 `shutdown_request`、`join(timeout=1)`。

## 6. 集成点

### 6.1 subagent(`task` 工具)

`task` 是普通工具,在 `agent_loop` 的 dispatch 分支走既有 `PreToolUse → dispatch → PostToolUse` 管线。`SubagentRunner.run(prompt)` 同步执行:

1. `messages = [{"role": "user", "content": prompt}]`,系统提示用 SUB_SYSTEM(只要求"完成任务并返回简洁结论")。
2. 循环至多 30 轮:`provider.chat(messages, base_tools.schemas())` → 无 tool_calls 即返回最终文本;有则逐条走 `hook_bus.first_block(PRE_TOOL_USE)` + `base_tools.dispatch`,追加 `role=tool` 结果。
3. 子循环**不**跑 compaction/jobs/memory/todo 注入;`base_tools` 是仅含 5 个基础工具的新 `ToolRegistry`(复用 `register_builtin_tools`),**无** `task`/团队/规划工具。

权限复用同一个 `HookBus`:子循环跑在派发线程——用户回合为主线程,交互审批正常;cron/团队回合为非主线程,`make_permission_hook` 已按 §7 直接拒绝。

### 6.2 团队回合(`harness.run_team_turn`)

队友完成/上报后,事件进入 Lead 收件箱,lead-inbox-processor 调用回调 `run_team_turn`(REPL 闭包绑定):

```python
def run_team_turn(self, messages) -> None:
    agents = self.agents
    events = agents.consume_and_inject_team(messages)
    if not events:
        return
    agent_loop(self, messages, "[team]")
    self.hooks.trigger(STOP, messages)
```

`consume_and_inject_team` 内做三件事(对应 s13 的 `consume_lead_inbox` + `format_team_events`):破坏性读取 Lead 收件箱 → 更新协议状态(`match_response`)→ 以 `[Team events]\n...` 追加一条 user 消息。团队事件是 best-effort(破坏性读),不回滚注入;与 cron 的 at-least-once 语义不同——任务板是持久真源,队友可据 `list_tasks` 恢复。

### 6.3 REPL 启动/停止

`repl` 增加团队运行时装配(与 jobs 并行):

```python
if jobs is not None:
    jobs.set_cron_turn(lambda: harness.run_scheduled_turn(messages))
    jobs.start()
if agents is not None:
    agents.set_team_turn(lambda: harness.run_team_turn(messages))
    agents.start()
# ...
finally:
    if agents is not None:
        agents.stop()
    if jobs is not None:
        jobs.stop()
```

用户回合:`with harness.agent_lock: harness.run_turn(messages, text)`(jobs 与 agents 共享同一把锁)。

## 7. 权限审批线程区分

队友跑在 daemon 线程,不能 `input()` 抢 stdin。队友工具复用与 Lead 相同的 `HookBus`(含 M2 已实现的 `make_permission_hook`),`first_block(PRE_TOOL_USE, event)` 先行:

- `allow` 规则(`read_file`/`write_file`/`edit_file`/`glob`,命中 `* * → allow`)→ 放行,队友可读写文件与列举。
- `deny` 规则(`git push --force*`、`rm -rf /*`)→ 拒绝。
- `ask` 规则(`bash * → ask`)→ 因队友在非主线程,`make_permission_hook` 返回 `denied: cannot request approval from a scheduled turn`。

**推论**:队友不能执行 `bash`(产品安全模型规定 bash 一律需交互审批,队友拿不到审批);`bash` 与危险操作由 Lead 执行。这比教程 s13 的"非破坏 bash 放行"更保守,但与产品既有"bash 必须审批"一致,且无需为队友另写一套危险命令正则。subagent(`task`)跑在派发线程:用户回合在主线程,交互审批正常;cron/团队回合在非主线程,bash 同样被拒。

## 8. 命名决策

统一 snake_case,延续产品既有工具参数约定:

| 教程(s13) | 本产品 |
|---|---|
| `addBlockedBy` / `blockedBy` | `add_blocked_by` / `blocked_by`(已在 M1.2 定) |
| `worktree` / `task_id` / `require_plan` | 不变 |
| 队友名 | `[A-Za-z0-9_-]{1,64}`,保留 `lead`/`agent`(不区分大小写判重) |
| 请求 ID | `req_{6 位随机}`(`random` 模块) |
| 收件箱目录 | `.mailboxes/`(`<name>.jsonl`) |
| worktree 目录/分支 | `.worktrees/<name>` / `wt/<name>` |
| 计划审批通知 | `plan_approval_request` / `plan_approval_response` / `plan_request` |
| 关机通知 | `shutdown_request` / `shutdown_response` |

## 9. 其余决策

- **Windows 无 `fcntl`**:教程 s13 用 `fcntl.flock` 做跨进程任务锁,本产品开发/运行环境是 Windows。决策:任务认领原子性仅用 `TeamRuntime` 的进程内 `threading.RLock` 保证;**跨进程原子认领明确列为非目标**(产品是单进程 REPL,与 M2 运行边界一致),不引入 `fcntl`/`msvcrt` 分支或新依赖。
- **`Task` 增加 `worktree` 字段**:`planning/tasks.py` 的 `Task` 追加 `worktree: str | None = None`;`TaskStore.load` 用 `Task(**data)` 构造,旧任务文件缺该键自动走默认值,向后兼容。`worktree` 仅作为数据字段被 `TaskStore` 存取;worktree 的解析/校验/create/remove 全在 `agents/worktree.py`。
- **worktree 依赖 `git`**:通过 `subprocess.run(["git", ...])`(列表参数,无 shell 插值)执行;`create_worktree` 仅 Lead 可用,失败但已留下分支/checkout 时返回 "Partial operation" 并保留工件供人工恢复。`remove_worktree` 是宿主函数,不注册为模型工具。
- **队友无任务时工作区工具报错**:队友的 `bash/read/write/edit/glob` 通过 assignment registry 解析 cwd;未认领任务返回 `Claim a Task before using workspace tools.`,不回退到仓库目录。
- **错误处理分层**(与 planning/jobs 一致):数据层错误(无效队友名、无效 task_id、worktree 校验失败、git 失败)返回普通字符串或抛 `ValueError`,由 `ToolRegistry.dispatch` 统一转 `error: ...`;业务拒绝(队友不存在、任务已认领、被依赖阻塞)返回普通字符串。
- **`.gitignore`**:追加 `.mailboxes/`、`.worktrees/`。
- **system_prompt**:追加一行团队引导("When parallel work would help, first propose a small team with clear responsibilities and wait for the user's confirmation. Do not call spawn_teammate before the user confirms."),与既有 compaction/planning/jobs 引导硬编码方式一致。
- **持久化文件**:收件箱是 JSONL(每行一条),读即删(destructive read);`MessageBus` 用 `threading.Condition` 支持 IDLE 短等待。
- **无新依赖**:subprocess/threading/dataclasses/pathlib/json 均为标准库。

## 10. 测试

- `tests/planning/test_tasks.py`:追加 `Task.worktree` 序列化/回填断言(旧文件缺键向后兼容)。
- `tests/agents/test_subagent.py`:SubagentRunner 嵌套 loop、基础工具分发、权限 hook 拦截、30 轮上限、无 task 工具。
- `tests/agents/test_bus.py`:MessageBus 发送/读取/破坏性读/并发唤醒/非法收件人名。
- `tests/agents/test_worktree.py`:名称校验、branch/路径解析、create/remove(用 tmp git 仓库)。
- `tests/agents/test_team.py`:TeamRuntime 认领原子性/assignment 注册表/plan gate/shutdown 与 plan 协议/收件箱消费注入。
- `tests/agents/test_teammate.py`:TeammateRuntime WORK/IDLE、收件箱处理、无任务工作区工具报错。
- `tests/agents/test_tools.py`:8 个工具 schema 与 handler 渲染。
- `tests/core/test_loop.py`:追加 `task` 工具 dispatch 集成测试(`make_harness` 加 `agents`)。
- `tests/cli/test_main.py`:追加 `build_harness` 装配 agents 断言。
- `tests/cli/test_repl.py`:追加 REPL 启动/停止 team runtime 断言。
