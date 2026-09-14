# blh-claude-code M5:编排与目标闭环 实现计划

- **日期**:2026-09-14
- **依据**:`docs/2026-09-14-m5-workflow-goals-design.md`
- **方法**:TDD,每个任务「失败测试 → 实现 → 验证 → commit」

## 任务总览

| # | 任务 | 产物 |
|---|---|---|
| 1 | workflow 基础:稳定 hash + JSON Schema + JSON 提取 | `workflow/schema.py` |
| 2 | journal 断点恢复 | `workflow/journal.py` |
| 3 | 运行时:runner + budget + ExecutionState 原语 | `workflow/runtime.py` |
| 4 | 工具 + 桥接 + 内置注册表 + 注册 | `workflow/tool.py` `registry.py` `tools.py` |
| 5 | goals:transcript + 评估器(OpenAI) | `goals/transcript.py` `evaluator.py` |
| 6 | goals:GoalController 六种 StopDecision | `goals/controller.py` |
| 7 | loop 集成(goal Stop hook) | `core/loop.py` |
| 8 | REPL `/goal` 命令 | `cli/repl.py` |
| 9 | Harness + main 装配 | `core/harness.py` `cli/main.py` |
| 10 | 收尾验证 | 全量测试 + ruff |

---

## 任务 1:workflow 基础(`workflow/schema.py`)

### 1.1 失败测试 `tests/workflow/test_schema.py`

```python
import pytest

from blh.workflow.schema import (MISS, SimpleJsonSchema, WorkflowInputError,
                                 _stable_hash, parse_runner_json)


def test_stable_hash_is_process_independent():
    assert _stable_hash("a") == _stable_hash("a")
    assert _stable_hash("a") != _stable_hash("b")


def test_schema_object_required():
    s = SimpleJsonSchema({"type": "object", "required": ["name"],
                          "properties": {"name": {"type": "string"}}})
    assert s.validate({"name": "x"}) == (True, None)
    assert s.validate({}) == (False, "missing required key 'name'")


def test_schema_array_items():
    s = SimpleJsonSchema({"type": "array",
                          "items": {"type": "integer"}})
    assert s.validate([1, 2]) == (True, None)
    assert s.validate([1, "x"]) == (False, "[1]: expected number")


def test_parse_runner_json_fenced():
    assert parse_runner_json("```json\n{\"a\": 1}\n```") == {"a": 1}


def test_parse_runner_json_invalid():
    with pytest.raises(WorkflowInputError):
        parse_runner_json("no json here")
```

### 1.2 实现

照搬 s16 的 `_stable_hash` / `SimpleJsonSchema` / `parse_runner_json`,并放 `MISS = object()` 哨兵与 `WorkflowInputError`。无 API 调用,纯函数。

### 1.3 验证

```powershell
uv run pytest tests/workflow/test_schema.py -q
```

### 1.4 commit

```
feat(workflow): add stable hash, JSON schema and runner-json parsing
```

---

## 任务 2:journal 断点恢复(`workflow/journal.py`)

### 2.1 失败测试 `tests/workflow/test_journal.py`

```python
import pytest

from blh.workflow.journal import WorkflowJournal
from blh.workflow.schema import MISS, WorkflowInputError


def test_key_is_deterministic(tmp_path):
    j = WorkflowJournal("wf_demo_0000000000000001", resume=False, store=tmp_path)
    assert j.key("agent", "l", "p", None) == j.key("agent", "l", "p", None)
    j.close()


def test_record_and_resume(tmp_path):
    store = tmp_path / ".runtime"
    j = WorkflowJournal("wf_demo_0000000000000001", resume=False, store=store)
    key = j.key("agent", "label", "prompt", None)
    j.record(key, {"v": 1})
    j.close()
    # 同参数 key 应稳定
    j2 = WorkflowJournal("wf_demo_0000000000000001", resume=True, store=store)
    assert j2.cached(key) == {"v": 1}
    j2.close()


def test_cached_miss(tmp_path):
    j = WorkflowJournal("wf_demo_0000000000000001", resume=False, store=tmp_path)
    assert j.cached("agent-0000000000") is MISS
    j.close()


def test_resume_missing_journal_raises(tmp_path):
    with pytest.raises(WorkflowInputError):
        WorkflowJournal("wf_demo_0000000000000001", resume=True, store=tmp_path)


def test_invalid_record_raises(tmp_path):
    store = tmp_path / ".runtime"
    store.mkdir()
    (store / "wf_demo_0000000000000001.journal.jsonl").write_text(
        "not json\n", encoding="utf-8")
    with pytest.raises(WorkflowInputError):
        WorkflowJournal("wf_demo_0000000000000001", resume=True, store=store)
```

### 2.2 实现

照搬 s16 `WorkflowJournal`,仅去掉 `STORE` 全局常量、`store` 改为构造参数(默认 None 时由调用方传入)。`MISS`、`_stable_hash`、`WorkflowInputError` 从 `schema` 导入。

### 2.3 验证

```powershell
uv run pytest tests/workflow/test_journal.py -q
```

### 2.4 commit

```
feat(workflow): add append-only journal with resume cache
```

---

## 任务 3:运行时(`workflow/runtime.py`)

### 3.1 失败测试 `tests/workflow/test_runtime.py`

用一个确定性 `MockRunner`(实现 `run(prompt, schema, label) -> RunnerOutput`)驱动 `ExecutionState`,不依赖真实 API。

```python
import asyncio

from blh.workflow.runtime import (Budget, ExecutionState, ExecutionLimits,
                                  MockWorkflowRunner, RunnerOutput)
from blh.workflow.schema import WorkflowInputError


class _Task:
    def __init__(self):
        self.usage = {"agents": 0, "tokens": 0}
        self.progress = []

    def progress_event(self, ptype, **data):
        self.progress.append({"type": ptype, **data})


def _state(tmp_path, journal, args=None):
    from blh.workflow.journal import WorkflowJournal
    journal = journal or WorkflowJournal("wf_demo_0000000000000001",
                                         resume=False, store=tmp_path)
    task = _Task()
    return ExecutionState(task, journal, MockWorkflowRunner(), Budget(), args or {}), task, journal


def test_agent_returns_value(tmp_path):
    state, task, journal = _state(tmp_path, None)
    value = asyncio.run(state.agent("hello"))
    assert value == "[mock] hello"
    assert task.usage["agents"] == 1
    journal.close()


def test_agent_schema_validates(tmp_path):
    state, task, journal = _state(tmp_path, None)
    schema = {"type": "object", "required": ["isReal"],
              "properties": {"isReal": {"type": "boolean"}}}
    value = asyncio.run(state.agent("is it real?", schema=schema, label="v"))
    assert value["isReal"] is True
    journal.close()


def test_parallel_barrier(tmp_path):
    state, task, journal = _state(tmp_path, None)
    values = asyncio.run(state.parallel([
        lambda: state.agent("a"),
        lambda: state.agent("b"),
    ]))
    assert values == ["[mock] a", "[mock] b"]
    journal.close()


def test_pipeline_order(tmp_path):
    state, task, journal = _state(tmp_path, None)
    async def stage(value, item, idx):
        return value + f"-{item}"
    values = asyncio.run(state.pipeline(["x", "y"], stage))
    assert values == ["x-x", "y-y"]
    journal.close()


def test_agent_resume_uses_cache(tmp_path):
    from blh.workflow.journal import WorkflowJournal
    j1 = WorkflowJournal("wf_demo_0000000000000001", resume=False, store=tmp_path)
    state, _, _ = _state(tmp_path, j1)
    asyncio.run(state.agent("same prompt", label="L"))
    j1.close()

    j2 = WorkflowJournal("wf_demo_0000000000000001", resume=True, store=tmp_path)
    state2, task2, _ = _state(tmp_path, j2)
    value = asyncio.run(state2.agent("same prompt", label="L"))
    assert value == "[mock] same prompt"
    assert task2.usage["agents"] == 1  # 回放也计数,但不重跑(见 progress 的 cached)
    assert task2.progress[-1]["status"] == "cached"
    j2.close()


def test_budget_exceeded(tmp_path):
    state, task, journal = _state(tmp_path, None)
    state.budget = Budget(total=0)
    with __import__("pytest").raises(WorkflowInputError):
        asyncio.run(state.agent("hello"))
    journal.close()
```

### 3.2 实现

- `RunnerOutput(value, tokens)`、`Budget`、`ExecutionLimits`、`ExecutionState` 照搬 s16,`MISS` 从 `schema` 导入。
- `agent()` 中缓存命中判断改为 `cached is not MISS`(s16 用 `MISS` 哨兵)。
- **新增 `OpenAIWorkflowRunner`**(核心适配):持 `provider`,用 `provider.client.chat.completions.create` 发无 tools 单轮,`max_tokens=2000`,system 提示沿用 s16 文案;从 `response.usage` 累加 `prompt_tokens + completion_tokens`;schema 时 `parse_runner_json` 解析失败回退原文(s16 语义)。
- **新增 `MockWorkflowRunner`**:确定性实现,`schema is None` 返回 `[mock] {prompt[:60]}`;含 `isReal` 返回 `{"isReal": True, ...}`;其余按 `required` 用稳定值填充。

### 3.3 验证

```powershell
uv run pytest tests/workflow/test_runtime.py -q
```

### 3.4 commit

```
feat(workflow): add execution state primitives and OpenAI runner
```

---

## 任务 4:工具 + 桥接 + 内置注册表 + 注册

### 4.1 失败测试

**`tests/workflow/test_tool.py`**(桥接 + 工具 schema)

```python
import asyncio

from blh.workflow.tool import run_workflow_sync
from blh.workflow.runtime import MockWorkflowRunner
from blh.workflow.registry import WORKFLOWS


def test_unknown_workflow_returns_error(tmp_path):
    out = run_workflow_sync(name="nope", store=tmp_path,
                            runner_factory=MockWorkflowRunner,
                            workflows=WORKFLOWS)
    assert "unknown workflow" in out


def test_run_sample_workflow(tmp_path):
    out = run_workflow_sync(name="review-changes",
                            args={"changes": "x = 1"},
                            store=tmp_path,
                            runner_factory=MockWorkflowRunner,
                            workflows=WORKFLOWS)
    assert "confirmed" in out
```

**`tests/workflow/test_registry.py`**

```python
from blh.workflow.registry import WORKFLOWS


def test_registry_contains_sample():
    assert "review-changes" in WORKFLOWS
    meta, fn = WORKFLOWS["review-changes"]
    assert meta["name"] == "review-changes"
    assert callable(fn)
```

**`tests/workflow/test_tools.py`**(注册进 ToolRegistry)

```python
from blh.workflow.tools import register_workflow_tools
from blh.workflow.runtime import MockWorkflowRunner
from blh.workflow.registry import WORKFLOWS
from blh.tools.registry import ToolRegistry


def test_registers_run_workflow(tmp_path):
    registry = ToolRegistry()
    register_workflow_tools(registry, store=tmp_path,
                            runner_factory=MockWorkflowRunner,
                            workflows=WORKFLOWS)
    names = [s["function"]["name"] for s in registry.schemas()]
    assert "run_workflow" in names
```

### 4.2 实现

- `tool.py`:`WorkflowTask`(task_id/run_id/meta/status/usage/progress + `progress_event`)、`validate_meta`、`workflow_run_lock`(threading.Lock 版,见设计文档 §3.4)、`WorkflowTool`(call/_call_locked/reserve_run_id/validate_run_id/read/write snapshot)、`run_workflow`、`run_workflow_sync`(=`asyncio.run(...)`,异常转字符串)。
- `registry.py`:内置 `WORKFLOWS = {"review-changes": (meta, sample_workflow)}`,样例工作流照搬 s16 的 pipeline(审计→逐条验证→筛真)。
- `tools.py`:`register_workflow_tools(registry, store, runner_factory, workflows)` 注册 `run_workflow`,handler 为闭包 `lambda name, args=None, resume_from_run_id=None: run_workflow_sync(...)`。
- 存储目录固定 `store = workdir/.workflow_runtime`(在 main 装配时传入)。

### 4.3 验证

```powershell
uv run pytest tests/workflow/test_tool.py tests/workflow/test_registry.py tests/workflow/test_tools.py -q
```

### 4.4 commit

```
feat(workflow): add workflow tool, registry and tool registration
```

---

## 任务 5:goals types + transcript + 评估器(OpenAI)

### 5.1 失败测试

**`tests/goals/test_types.py`** 与 **`tests/goals/test_transcript.py`**

```python
from blh.goals.transcript import transcript_text


def test_plain_assistant_with_tool_calls():
    messages = [
        {"role": "assistant", "content": None,
         "tool_calls": [{"function": {"name": "bash",
                                      "arguments": "{\"command\": \"ls\"}"}}]},
    ]
    text = transcript_text(messages)
    assert "tool_call" in text
    assert "bash" in text


def test_tool_result_rendered():
    messages = [{"role": "tool", "content": "exit_code=0"}]
    assert "tool_result" in transcript_text(messages)


def test_truncates_oversized_newest_drops_older():
    # 最新一条超长:只截该条(带 omitted 标记),更旧消息被丢弃
    messages = [{"role": "user", "content": "first"},
                {"role": "user", "content": "second"},
                {"role": "user", "content": "x" * 5000}]
    text = transcript_text(messages, max_characters=100)
    assert "omitted" in text
    assert "first" not in text


def test_keeps_recent_complete_messages():
    messages = [{"role": "user", "content": "first"},
                {"role": "user", "content": "second"}]
    text = transcript_text(messages, max_characters=1000)
    assert "USER:\nfirst" in text
    assert "USER:\nsecond" in text
```

**`tests/goals/test_evaluator.py`**(假 provider)

```python
from blh.goals.evaluator import PromptGoalEvaluator
from blh.goals.types import GoalError


class _FakeProvider:
    def __init__(self, text):
        self._text = text
        self.calls = []

    def chat(self, messages, tools, max_tokens=None):
        self.calls.append((messages, tools, max_tokens))
        return {"role": "assistant", "content": self._text}


def test_evaluate_ok():
    provider = _FakeProvider('{"ok": true, "reason": "done", "impossible": false}')
    result = PromptGoalEvaluator(provider).evaluate("x", [{"role": "user", "content": "hi"}])
    assert result.ok is True
    assert result.reason == "done"
    # 评估器必须无 tools、且带 max_tokens
    assert provider.calls[0][1] == []
    assert provider.calls[0][2] == 512


def test_evaluate_invalid_json_raises():
    provider = _FakeProvider("not json")
    import pytest
    with pytest.raises(GoalError):
        PromptGoalEvaluator(provider).evaluate("x", [])
```

### 5.2 实现

- `types.py`:`GoalError`、`GoalState`、`GoalEvaluation`、`StopDecision`(照搬 s17 字段)。
- `transcript.py`:`_plain_content`(OpenAI 格式,见设计文档 §5.1)、`transcript_text`(照搬 s17 截断逻辑)。
- `evaluator.py`:`_parse_json_object`(照搬 s17 严格校验)+ `PromptGoalEvaluator`:
  - `evaluate(condition, messages) -> GoalEvaluation`,同步。
  - 用 `provider.chat([system, user], tools=[], max_tokens=512)`,system 文案沿用 s17,`tools=[]` 会被 provider 归一为 `None`。
  - 从 `response["content"]` 解析并返回 `GoalEvaluation(**value)`。

### 5.3 验证

```powershell
uv run pytest tests/goals/test_types.py tests/goals/test_transcript.py tests/goals/test_evaluator.py -q
```

### 5.4 commit

```
feat(goals): add transcript rendering and OpenAI goal evaluator
```

---

## 任务 6:GoalController 六种 StopDecision

### 6.1 失败测试 `tests/goals/test_controller.py`

用假 evaluator(返回预设 `GoalEvaluation`)驱动,覆盖 `allow/block/achieved/failed/limit/error`:

```python
import pytest

from blh.goals.controller import GoalController
from blh.goals.types import GoalEvaluation, GoalError


class _Evaluator:
    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def evaluate(self, condition, messages):
        self.calls += 1
        return self._results.pop(0)


def test_no_goal_allow():
    ctrl = GoalController(_Evaluator([]))
    assert ctrl.evaluate_after_turn([]).action == "allow"


def test_ok_achieved():
    ctrl = GoalController(_Evaluator([GoalEvaluation(True, "done")]))
    ctrl.set_goal("do it")
    decision = ctrl.evaluate_after_turn([])
    assert decision.action == "achieved"
    assert ctrl.active is None


def test_impossible_failed():
    ctrl = GoalController(_Evaluator([GoalEvaluation(False, "cannot", impossible=True)]))
    ctrl.set_goal("do it")
    assert ctrl.evaluate_after_turn([]).action == "failed"


def test_block_then_limit():
    results = [GoalEvaluation(False, "still missing")] * 20
    ctrl = GoalController(_Evaluator(results), block_cap=8)
    ctrl.set_goal("do it")
    actions = [ctrl.evaluate_after_turn([]).action for _ in range(9)]
    assert actions[:8] == ["block"] * 8
    assert actions[8] == "limit"


def test_clear():
    ctrl = GoalController(_Evaluator([]))
    ctrl.set_goal("do it")
    assert "cleared" in ctrl.clear().lower()
    assert ctrl.active is None


def test_set_goal_empty_raises():
    with pytest.raises(GoalError):
        GoalController(_Evaluator([])).set_goal("   ")


def test_background_defer():
    ctrl = GoalController(_Evaluator([GoalEvaluation(False, "x")]))
    ctrl.set_goal("do it")
    assert ctrl.evaluate_after_turn([], background_running=True).action == "defer"
```

### 6.2 实现

`controller.py`:`GoalController(evaluator, block_cap=8, events=None)` 同步版,`set_goal/clear/status/evaluate_after_turn/_record/restore` 照搬 s17,去掉 `async/await` 与 `time` 依赖的 token 入参保留默认 0。`evaluate_after_turn` 顺序:`无 goal→allow` → `background_running→defer` → 调用 evaluator(异常→error)→ `ok→achieved` → `impossible→failed` → 累计 block → 超 `block_cap→limit` → 否则 `block`。

### 6.3 验证

```powershell
uv run pytest tests/goals/test_controller.py -q
```

### 6.4 commit

```
feat(goals): add synchronous GoalController with stop decisions
```

---

## 任务 7:loop 集成(goal Stop hook)

### 7.1 失败测试(追加到 `tests/core/test_loop.py`)

```python
def test_goal_block_continues_and_achieved_returns():
    # 用 MockProvider 脚本化:第一次返回无 tool_calls,评估器 block;
    # 第二次返回无 tool_calls,评估器 achieved。断言消息里注入 [Goal still active]。
    ...
```

> 具体实现依赖 `make_harness` 增加 `goal=` 参数与 `MockProvider`。测试断言:block 时 `[Goal still active]` 出现在 messages,且 loop 又调用了 provider;achieved 时 loop 返回。

### 7.2 实现

`core/loop.py` 的 `if not tool_calls:` 分支改为:

```python
if not tool_calls:
    decision = _evaluate_goal_stop(harness, messages)
    if decision is not None and decision.action == "block":
        messages.append({"role": "user",
                         "content": _goal_reminder(harness.goal, decision)})
        continue
    return
```

并新增两个辅助函数:

```python
def _evaluate_goal_stop(harness, messages):
    goal = getattr(harness, "goal", None)
    if goal is None:
        return None
    background_running = bool(harness.jobs
                              and harness.jobs.background.has_running())
    return goal.evaluate_after_turn(messages, background_running=background_running)


def _goal_reminder(goal, decision):
    condition = goal.active.condition if goal.active else ""
    return (f"[Goal still active]\nCondition: {condition}\n"
            f"Evaluator: {decision.reason}\n"
            "Continue working and surface the missing evidence.")
```

同时 `jobs/background.py` 增加 `has_running()`:

```python
def has_running(self) -> bool:
    with self._lock:
        return any(t.get("status") == "running" for t in self.tasks.values())
```

### 7.3 验证

```powershell
uv run pytest tests/core/test_loop.py -q
```

### 7.4 commit

```
feat(core): add goal stop hook at agent loop return boundary
```

---

## 任务 8:REPL `/goal` 命令

### 8.1 失败测试(追加到 `tests/cli/test_repl.py`)

用假 harness(带 goal 控制器)与 monkeypatch 的 `input`,断言:
- 输入 `/goal` → 打印状态,不进入 `run_turn`。
- 输入 `/goal clear` → 打印清除,不进入 `run_turn`。
- 输入 `/goal 完成条件` → 调 `set_goal` 且 `run_turn` 收到的是去掉 `/goal ` 前缀的条件文本。

### 8.2 实现

`cli/repl.py` 在 `harness.run_turn(messages, text)` 之前加:

```python
if harness.goal is not None:
    cmd = harness.goal_command(text)
    if cmd == "status":
        print(harness.goal.status(0)); continue
    if cmd == "clear":
        print(harness.goal.clear()); continue
    if cmd == "set":
        harness.goal.set_goal(text[6:].strip())
        text = text[6:].strip()
```

> `goal_command(text)` 在 `core/harness.py` 提供,返回 `"status"/"clear"/"set"/None`;`/goal <clear 别名>` 归为 `clear`。

### 8.3 验证

```powershell
uv run pytest tests/cli/test_repl.py -q
```

### 8.4 commit

```
feat(cli): handle /goal command in REPL
```

---

## 任务 9:Harness + main 装配

### 9.1 失败测试

**追加 `tests/core/test_loop.py`**:`make_harness` 增加 `workflow`/`goal` 参数透传。

**追加 `tests/cli/test_main.py`**:

```python
def test_build_harness_wires_workflow_and_goal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.goal is not None
    assert harness.workflow is not None
    names = [s["function"]["name"] for s in harness.tools.schemas()]
    assert "run_workflow" in names
```

### 9.2 实现

- `core/harness.py`:`__init__` 加 `workflow=None`、`goal=None`;新增 `goal_command(text)`(解析 `/goal` 前缀);`system_prompt()` 追加 goal/workflow 使用说明(可选)。
- `cli/main.py`:
  - 导入 `PromptGoalEvaluator`、`GoalController`、`OpenAIWorkflowRunner`、`register_workflow_tools`、`WORKFLOWS`。
  - 构造 `workflow_store = wd / ".workflow_runtime"`,用 `OpenAIWorkflowRunner(provider)` 作为 `runner_factory`,`register_workflow_tools(tools, store=workflow_store, runner_factory=..., workflows=WORKFLOWS)`。
  - 构造 `goal = GoalController(PromptGoalEvaluator(provider))`。
  - `Harness(...)` 增加 `workflow`、`goal` 参数。

### 9.3 验证

```powershell
uv run pytest tests/core/test_loop.py tests/cli/test_main.py -q
```

### 9.4 commit

```
feat(cli): assemble workflow and goal in build_harness
```

---

## 任务 10:收尾验证

```powershell
uv run pytest -q
uv run ruff check src/blh tests
```

两项均通过后,更新 `docs/2026-09-14-m5-workflow-goals-design.md` 状态为「已实施」,汇总 M5 完成。


