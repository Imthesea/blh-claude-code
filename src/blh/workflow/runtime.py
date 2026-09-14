"""workflow 运行时:runner、budget、ExecutionState 编排原语。"""

import asyncio
import json
from dataclasses import dataclass

from .schema import (
    MISS,
    SimpleJsonSchema,
    WorkflowInputError,
    _stable_hash,
    parse_runner_json,
)

AGENT_CAP = 1000
CONCURRENCY = 8


@dataclass(frozen=True)
class RunnerOutput:
    value: object
    tokens: int


class OpenAIWorkflowRunner:
    """workflow 子 agent:无 tools 单轮,复用 host 的 OpenAI client。"""

    def __init__(self, provider):
        self.provider = provider

    def run(self, prompt, schema=None, label=None):
        request = prompt
        if schema is not None:
            request += ("\n\nReturn only one JSON object matching this schema:\n"
                        + json.dumps(schema, ensure_ascii=True, sort_keys=True))
        response = self.provider.client.chat.completions.create(
            model=self.provider.config.model,
            messages=[
                {"role": "system",
                 "content": ("You are a focused workflow agent. Complete only "
                             "the supplied step. Do not claim access to files "
                             "or results not included in the prompt.")},
                {"role": "user", "content": request},
            ],
            max_tokens=2000,
        )
        message = response.choices[0].message
        text = message.content or ""
        if schema is None:
            value = text
        else:
            try:
                value = parse_runner_json(text)
            except WorkflowInputError:
                value = text
        usage = response.usage
        tokens = int(getattr(usage, "prompt_tokens", 0) or 0) + int(
            getattr(usage, "completion_tokens", 0) or 0)
        return RunnerOutput(value, tokens)


class MockWorkflowRunner:
    """确定性 runner,用于单元测试与无 API 场景。"""

    def run(self, prompt, schema=None, label=None):
        if schema is None:
            return RunnerOutput(f"[mock] {prompt[:60]}", len(prompt) // 4)
        props = schema.get("properties", {})
        if "isReal" in props:
            value = {"isReal": True, "reason": "reproduced"}
        else:
            value = {}
            for key in schema.get("required", []):
                sub = schema.get("properties", {}).get(key) or {}
                t = sub.get("type")
                if t == "array":
                    value[key] = []
                elif t == "boolean":
                    value[key] = _stable_hash(prompt + key) % 4 != 0
                elif t in ("number", "integer"):
                    value[key] = _stable_hash(prompt + key) % 5
                else:
                    value[key] = f"{label or key}-value"
        return RunnerOutput(value, len(prompt) // 4 + 8)


class Budget:
    def __init__(self, total=None):
        self.total = total
        self._spent = 0

    def add(self, n):
        if self.total is not None and self._spent + n > self.total:
            raise WorkflowInputError(
                f"token budget exceeded ({self._spent + n} > {self.total})")
        self._spent += n

    def remaining(self):
        return float("inf") if self.total is None else max(0, self.total - self._spent)


class ExecutionLimits:
    def __init__(self):
        self.agents = 0
        self.semaphore = asyncio.Semaphore(CONCURRENCY)

    def claim_agent(self):
        self.agents += 1
        if self.agents > AGENT_CAP:
            raise WorkflowInputError(f"agent() cap reached ({AGENT_CAP})")


class ExecutionState:
    def __init__(self, task, journal, runner, budget, args, depth=0,
                 limits=None, workflows=None):
        self.task = task
        self.journal = journal
        self.runner = runner
        self.budget = budget
        self.args = args
        self._depth = depth
        self._phase = None
        self._phases_seen = set()
        self._limits = limits or ExecutionLimits()
        self._workflows = workflows or {}

    def phase(self, title):
        self._phase = title
        if title not in self._phases_seen:
            self._phases_seen.add(title)
            self.task.progress_event("workflow_phase", title=title)

    def log(self, message):
        self.task.progress_event("workflow_log", message=message)

    async def agent(self, prompt, schema=None, label=None, phase=None):
        label = label or (prompt[:24] + "...")
        self._limits.claim_agent()
        if self.budget.remaining() <= 0:
            raise WorkflowInputError("token budget exceeded")
        key = self.journal.key("agent", label, prompt, schema)
        cached = self.journal.cached(key)
        if cached is not MISS:
            if schema is not None:
                ok, err = SimpleJsonSchema(schema).validate(cached)
                if not ok:
                    raise WorkflowInputError(
                        f"cached agent output failed schema validation: {err}")
            self.task.progress_event("workflow_agent", label=label,
                                     phase=phase or self._phase, status="cached")
            return cached
        async with self._limits.semaphore:
            run = await asyncio.to_thread(self.runner.run, prompt, schema, label)
            result, tokens = run.value, run.tokens
        if schema is not None:
            ok, err = SimpleJsonSchema(schema).validate(result)
            if not ok:
                retry = await asyncio.to_thread(
                    self.runner.run, prompt + "\n\nReturn valid JSON.",
                    schema, label)
                result, tokens = retry.value, tokens + retry.tokens
                ok, err = SimpleJsonSchema(schema).validate(result)
                if not ok:
                    raise WorkflowInputError(
                        f"agent({{schema}}) invalid output: {err}")
        self.budget.add(tokens)
        self.task.usage["agents"] += 1
        self.task.usage["tokens"] += tokens
        self.journal.record(key, result)
        self.task.progress_event("workflow_agent", label=label,
                                 phase=phase or self._phase, status="done")
        return result

    async def parallel(self, thunks):
        return await asyncio.gather(*[thunk() for thunk in thunks])

    async def pipeline(self, items, *stages):
        async def run_item(item, idx):
            value = item
            for stage in stages:
                value = await stage(value, item, idx)
            return value
        return await asyncio.gather(*[run_item(it, i) for i, it in enumerate(items)])

    async def workflow(self, name, args=None):
        if self._depth >= 1:
            raise WorkflowInputError("workflow() nesting is one level only")
        if name not in self._workflows:
            raise WorkflowInputError(f"unknown workflow '{name}'")
        _meta, fn = self._workflows[name]
        child = ExecutionState(self.task, self.journal, self.runner, self.budget,
                               args or {}, depth=self._depth + 1,
                               limits=self._limits, workflows=self._workflows)
        return await fn(child, args or {})
