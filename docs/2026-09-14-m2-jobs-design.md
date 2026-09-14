# blh-claude-code M2:异步与调度(jobs) 设计

- **日期**:2026-09-14
- **状态**:设计已批准,待编写实现计划
- **来源**:learn-claude-code s11(background tasks)、s12(cron scheduler)
- **整体设计**:`../2026-09-13-blh-claude-code-design.md`(§4.1 将 s11/s12 归并为 `jobs` 包,§7 里程碑 M2)

---

## 1. 目标

新增 `blh.jobs` 包,提供两类异步能力,让 Agent Loop 不被慢操作阻塞、能按本地时间自动启动一轮工作:

1. **后台任务(s11)**——bash 工具新增 `run_in_background` 参数,耗时命令放入 daemon 线程执行,当前工具调用先返回占位 `bg_id`,后续轮次以 `<task_notification>` 注入完成结果。
2. **cron 调度(s12)**——`schedule_cron`/`list_crons`/`cancel_cron` 三个工具 + 调度线程 + 队列处理线程,到点把 `[Scheduled] prompt` 注入会话并自动跑一轮 Agent Loop,`.scheduled_tasks.json` 持久化。

两者共享"异步单元 + 完成通知注入"模型(主设计文档 §4.2 的归并理由),但生命周期不同:后台任务随进程消失(不持久化),cron 的 `durable=True` 任务跨进程留存。

## 2. 范围

| 项 | 来源 | 说明 |
|---|---|---|
| bash 参数 `run_in_background` | s11 | 显式 `true` 才走后台路径,不猜测关键词 |
| `schedule_cron` | s12 | 五段式 cron 表达式 + prompt,`recurring`/`durable` 可选 |
| `list_crons` | s12 | 一行摘要列出所有 cron 任务 |
| `cancel_cron` | s12 | 按 ID 取消 |

## 3. 包结构

```
src/blh/jobs/
  __init__.py    # 空
  background.py  # BackgroundManager:后台线程执行 + 完成队列 + collect 通知
  cron.py        # cron 表达式纯函数 + CronJob dataclass + CronScheduler(持久化/队列)
  runtime.py     # JobsRuntime:组合两者 + agent_lock + 线程生命周期 + 注入
  tools.py       # register_jobs_tools:schedule_cron/list_crons/cancel_cron
```

- `background.py` 与 `cron.py` 互不依赖;`runtime.py` 组合两者;`tools.py` 只依赖 `cron.py`,做模型消息字符串渲染。
- `cron.py` 的纯函数(`cron_matches`/`validate_cron`)与 `CronScheduler` 分离,便于独立测试。

## 4. 状态归属(无全局状态)

教程用模块级全局(`BACKGROUND`、`scheduled_jobs`、`cron_queue`、`session_history`、`agent_lock`),产品全部收敛为显式对象:

- `BackgroundManager`、`CronScheduler` 由 `build_harness` 创建,组合成 `JobsRuntime`,挂到 `Harness.jobs`。
- `Harness.__init__` 增加可选第 8 参 `jobs=None`(默认 None 保持 M0/M1 行为不变)。
- 会话 `messages` 由 REPL 持有;cron 队列处理线程通过 `JobsRuntime` 注入的**回调**(`set_cron_turn`)访问同一会话,回调由 REPL 闭包绑定,`runtime.py` 不 import `Harness`,避免循环依赖。

## 5. 线程模型与锁

| 线程 | 来源 | 职责 |
|---|---|---|
| 主线程(REPL) | 既有 | 用户回合:`input` → `harness.run_turn` |
| cron-scheduler(daemon) | s12 | 每秒 `cron.poll_due(datetime.now())`,到期任务入内存队列 |
| cron-queue-processor(daemon) | s12 | 每 0.2s 检查队列,拿到 `agent_lock` 后跑一轮 cron 回合 |

- **`agent_lock`**:用户回合(主线程)与 cron 回合(队列处理线程)互斥访问同一 `messages`。REPL 的每个用户回合用 `with harness.jobs.agent_lock:` 包裹;队列处理线程用 `acquire(blocking=False)` 抢锁,抢不到就跳过(等 agent 空闲)。
- **线程只在 REPL 启动**:`-p` 一次性模式不启动调度线程(调度需持续运行才有意义)。`JobsRuntime.start()`/`stop()` 幂等,`stop()` 置 `Event` 并 `join(timeout=1)`。
- daemon 线程随进程退出;cron 只在 Agent 进程存活时按时触发(与教程一致的运行边界)。

## 6. loop / harness / repl 集成

### 6.1 后台结果注入(`agent_loop` 开头)

每次调用 `provider.chat` 前,收集已完成的后台结果,以 user 消息注入(OpenAI 协议 content 是 `str`,直接 `append` 一条 user 消息,无需教程里对 Anthropic list content 的适配):

```python
if harness.jobs is not None:
    harness.jobs.inject_background_results(messages)
```

### 6.2 后台执行(dispatch bash 时)

`agent_loop` 的 tool 循环里,`bash` + `run_in_background is True` 走后台路径,不调用同步 dispatch(与既有 `compact` 拦截同模式):

```python
elif harness.jobs is not None and name == "bash" and event["input"].get("run_in_background") is True:
    blocked = harness.hooks.first_block(PRE_TOOL_USE, event)
    if blocked is not None:
        result = blocked
    else:
        result = harness.jobs.start_background(event["input"].get("command", ""))
        harness.hooks.trigger(POST_TOOL_USE, event, result)
```

权限审批仍先跑(`PreToolUse`),再决定是否后台。

### 6.3 cron 交付(`harness.run_scheduled_turn`)

cron 回合不触发 `USER_PROMPT_SUBMIT`、不做 memory 提取(自动任务非用户交互),只做:`consume_and_inject_cron` → `agent_loop` → `STOP` → ack;`agent_loop` 抛异常时回滚注入的消息并恢复队列:

```python
def run_scheduled_turn(self, messages) -> None:
    jobs = self.jobs
    fired = jobs.consume_and_inject_cron(messages)
    if not fired:
        return
    try:
        agent_loop(self, messages, "[scheduled]")
    except Exception:
        jobs.restore_cron(messages, fired)
        raise
    else:
        jobs.cron.acknowledge(fired)
        self.hooks.trigger(STOP, messages)
```

ack 发生在整个 cron 回合正常结束后(教程在首次模型响应后 ack);产品简化但保留 at-least-once 语义:中途失败会重新交付整条 `[Scheduled] prompt`。

## 7. 权限审批线程区分

cron 回合跑在队列处理线程(非主线程),不能 `input()` 抢 stdin。沿用教程 s12 语义:非主线程的工具审批**直接拒绝**(`denied: cannot request approval from a scheduled turn`)。

`make_permission_hook` 内部在调用 `ask_fn` 前判断 `threading.current_thread() is threading.main_thread()`,非主线程直接返回拒绝字符串。主线程(REPL 用户回合与 `-p`)行为不变。

## 8. 命名决策

沿用教程标识符(已是 snake_case),与产品既有约定一致:

| 项 | 值 |
|---|---|
| 后台任务 ID | `bg_0001`(`bg_{counter:04d}`) |
| cron 任务 ID | `cron_{8 位 hex}`(`secrets.token_hex(4)`) |
| 后台通知 | `<task_notification>` 含 `<task_id>`/`<status>`/`<command>`/`<summary>` |
| cron 交付 | `[Scheduled] {prompt}` |
| 持久化文件 | `.scheduled_tasks.json` |

## 9. 其余决策

- **后台执行不复用 `tools/bash.py` 的 `run_bash`**:后者返回 `str` 丢失 exit code,无法区分 completed/failed。`background.py` 内用 `subprocess.run` 独立实现 `_run_bash_process`,返回 `(output, exit_code)`(超时自动 kill 进程,跨平台安全);`exit_code == 0` → completed,其余(非零/超时/OSError)→ failed。
- **cron 表达式零新依赖**:手写 `validate_cron`/`cron_matches`,支持 `*`、`*/N`、`N`、`N-M`、`N,M,...` 五段式,直接移植教程 s12。
- **错误处理分层**(与 planning 一致):数据层错误(`validate_cron` 失败、prompt 空、无效 job ID)抛 `ValueError`,由 `ToolRegistry.dispatch` 统一转 `error: ...`;业务拒绝(`cancel` 不存在的任务)返回普通字符串。
- **持久化原子写**:`.scheduled_tasks.json` 用临时文件 + `os.replace()` 更新;`load` 遇损坏文件打印日志不抛,跳过非法条目。`durable=False` 只存内存。
- **`.gitignore`**:追加 `.scheduled_tasks.json`。
- **system_prompt**:追加一行引导("Set run_in_background only for independent Bash commands. Use schedule_cron for work that should start at a future local time."),与既有 compaction/planning 引导硬编码方式一致。

## 10. 测试

- `tests/jobs/test_background.py`:BackgroundManager 注册/后台执行/完成通知/空命令拒绝。
- `tests/jobs/test_cron.py`:cron 表达式解析校验匹配 + CronScheduler 增删查/持久化/队列/ack/restore。
- `tests/jobs/test_runtime.py`:JobsRuntime 组合、注入、线程 start/stop 幂等。
- `tests/jobs/test_tools.py`:3 个工具 schema 与 handler 渲染。
- `tests/core/test_loop.py`:追加后台 dispatch 与注入集成测试(`make_harness` 加 `jobs`)。
- `tests/tools/test_builtin.py`:追加 bash schema 含 `run_in_background` 断言。
- `tests/security/test_approval.py`:追加非主线程拒绝断言。
- `tests/cli/test_main.py`:追加 `build_harness` 装配 jobs 断言。
- `tests/cli/test_repl.py`:追加 REPL 启动/停止 runtime 断言。
