# blh-claude-code M5:编排与目标闭环 设计文档

- **日期**:2026-09-14
- **状态**:已实施
- **来源**:learn-claude-code s16(workflow runtime) + s17(goal loop)

---

## 1. 目标

新增两个包,补齐「编排 + 目标闭环」:

1. **`blh.workflow`**:内置 trusted 工作流注册表。一次工具调用跑完整编排,支持 journal 断点恢复。
2. **`blh.goals`**:session 级 goal + 独立评估器,在 agent loop 的停止边界判定「继续 or 结束」。

设计文档 M5 验收:工作流断点恢复;评估器控制停止/续行。

## 2. 已确认决策

| 决策点 | 结论 |
|---|---|
| workflow 脚本来源 | 内置注册表:host 硬编码 trusted Python 函数,模型只传 `name`/`args`/`resume_from_run_id` |
| goal 触发方式 | REPL `/goal` 命令:`/goal` 查状态、`/goal clear` 清除、`/goal <条件>` 设定并执行 |

## 3. 关键适配(教程 Anthropic → 本项目 OpenAI)

1. **消息格式**:项目内部为 OpenAI 格式(`assistant.tool_calls[]` + `role=tool`)。goal 评估器读的 transcript、workflow 子 agent 的入参都按此格式渲染。
2. **模型调用**:workflow 子 agent 与 goal 评估器都是「无 tools 的单轮 chat」。子 agent 复用 `provider.client`(拿 `usage` 记账),评估器复用 `provider.chat(messages, tools=[])`。
3. **同步化**:blh 的 `agent_loop` 是同步的。goal 评估改为同步;workflow 运行时保留 s16 的 async 编排原语,由同步工具 handler 用 `asyncio.run` 桥接。
4. **文件锁**:s16 的 `fcntl.flock` 在 Windows 不可用。blh 单进程,改用 `threading.Lock`(进程内互斥)+ `reserve_run_id` 的 `O_EXCL` 文件预留(跨进程 runId 唯一),去掉 fcntl 依赖。

## 4. workflow 包结构

```
src/blh/workflow/
  __init__.py
  schema.py   # SimpleJsonSchema + 稳定 hash + JSON 提取
  journal.py  # WorkflowJournal(jsonl 逐行,resume 回放缓存)
  runtime.py  # ExecutionState(agent/parallel/pipeline/phase/log/workflow) + Budget + OpenAI runner
  tool.py     # WorkflowTool + run_workflow + run_workflow_sync 桥接
  registry.py # WORKFLOWS 内置注册表 + 样例工作流
  tools.py    # register_workflow_tools
```

### 4.1 运行时护栏与标识

- `AGENT_CAP=1000`、`CONCURRENCY=8`(asyncio.Semaphore)。
- `_stable_hash(s) = int(sha256(s).hexdigest(), 16)`:跨进程稳定,作为 journal 断点 key 的取模基础。
- `run_id` 形如 `wf_{name}_{token_hex(8)}`,`reserve_run_id` 用 `os.open(O_CREAT|O_EXCL)` 预留唯一快照文件。
- `WorkflowInputError` 承载所有「非法输入/非法恢复/预算超限」错误,工具 handler 捕获后转字符串返回。

### 4.2 journal 断点恢复

`WorkflowJournal(run_id, resume, store)`:

- 非 resume:以 `w` 打开 `{run_id}.journal.jsonl`(截断)。
- resume:读已有 journal 逐行 `json.loads`,校验 `{key, value}` 结构,重建 `cache`;以 `a` 追加。
- `key(kind, label, prompt, schema)`:由 `kind|label|prompt|schema(排序)` 做 `_stable_hash % 10**10` 得稳定语义 key,并发顺序无关。
- `agent()` 先查 `cached(key)`,命中则直接回放(schema 命中时先校验),不重跑。

### 4.3 编排原语(注入 ExecutionState)

- `phase(title)`、`log(message)`:进度事件。
- `agent(prompt, schema=None, label=None)`:单子 agent;schema 时校验输出,失败重试一次。
- `parallel(thunks)`:barrier,全并发,任一失败整体失败。
- `pipeline(items, *stages)`:逐项流水,项间无 barrier。
- `workflow(name, args)`:子工作流,仅一层嵌套。

### 4.4 工具与桥接

- 工具名 `run_workflow`,参数 `name`(必填)/`args`/`resume_from_run_id`。
- 同步 handler `run_workflow_sync(**kwargs)` = `asyncio.run(run_workflow(**kwargs))`,异常转字符串。
- `WorkflowTool.call` 流程:validate_meta → check_permission → 预留/校验 run_id → 上锁 → 执行 → 写 snapshot/output/last_run。

## 5. goals 包结构

```
src/blh/goals/
  __init__.py
  types.py      # GoalError / GoalState / GoalEvaluation / StopDecision
  transcript.py # OpenAI 格式 transcript 渲染 + 截断
  evaluator.py  # PromptGoalEvaluator(OpenAI,无 tools)
  controller.py # GoalController(set/clear/status/evaluate_after_turn/restore)
```

### 5.1 transcript(OpenAI 格式)

- `_plain_content(message)`:按 role 渲染:
  - `assistant`:正文 + `tool_calls[]` → `[tool_call {name} {arguments}]`。
  - `tool`:正文 → `[tool_result {content}]`。
  - 其余:正文字符串。
- `transcript_text(messages, max_characters)`:保留最近完整消息,仅裁剪超长最新一条。

### 5.2 评估器与控制循环

- `PromptGoalEvaluator.evaluate(condition, messages) -> GoalEvaluation(ok, reason, impossible)`:
  拼 JSON payload → `provider.chat(无 tools, max_tokens=512)` → 严格解析 `{ok, reason, impossible}`。
- `GoalController.evaluate_after_turn(messages, background_running=False) -> StopDecision`:
  - 无 goal → `allow`。
  - 后台运行中 → `defer`。
  - `ok` → `achieved`(清 goal);`impossible` → `failed`;连续 block 超 `block_cap=8` → `limit`;否则 → `block`。
- `set_goal`/`clear`/`status`/`restore` 沿用 s17 语义,评估与决策全部同步。

## 6. 集成

- **`core/loop.py`**:在 `not tool_calls` 的 return 边界,若 `harness.goal` 存在,调 `evaluate_after_turn`;`block` 则追加 `[Goal still active]` 用户消息后 `continue`,否则 `return`。
- **`core/harness.py`**:新增 `workflow`、`goal` 字段(默认 None),提供 `evaluate_goal_stop()` 与 `handle_goal_command()`。
- **`cli/main.py`**:`build_harness` 构造 workflow 运行时 + goal 控制器 + 评估器,注册 `run_workflow` 工具,传入 Harness。
- **`cli/repl.py`**:识别 `/goal` 命令;`/goal`/`/goal clear` 打印后跳过 turn,`/goal <条件>` 设 goal 后把条件作为本轮 user 请求继续。

## 7. 测试策略

- `workflow`:SimpleJsonSchema 校验、journal 断点(记录/回放/稳定 key/非法记录)、ExecutionState 原语(用 `MockRunner`)、工具注册与桥接。
- `goals`:transcript 渲染(OpenAI)、评估器(假 provider)、GoalController 六种 StopDecision。
- 集成:loop 在 goal `block` 时续行、`achieved` 时返回;`build_harness` 装配 workflow+goal。
- 全部 mock provider,不依赖真实 API;沿用 `tests/` 镜像 `src/` 结构。
