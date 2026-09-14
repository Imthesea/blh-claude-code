import asyncio

import pytest

from blh.workflow.runtime import Budget, ExecutionState, MockWorkflowRunner
from blh.workflow.schema import WorkflowInputError

RUN_ID = "wf_demo_0000000000000001"


class _Task:
    def __init__(self):
        self.usage = {"agents": 0, "tokens": 0}
        self.progress = []

    def progress_event(self, ptype, **data):
        self.progress.append({"type": ptype, **data})


def _state(tmp_path, journal=None, args=None):
    from blh.workflow.journal import WorkflowJournal
    if journal is None:
        journal = WorkflowJournal(RUN_ID, resume=False, store=tmp_path)
    task = _Task()
    state = ExecutionState(task, journal, MockWorkflowRunner(), Budget(),
                           args or {})
    return state, task, journal


def test_agent_returns_value(tmp_path):
    state, task, journal = _state(tmp_path)
    value = asyncio.run(state.agent("hello"))
    assert value == "[mock] hello"
    assert task.usage["agents"] == 1
    journal.close()


def test_agent_schema_validates(tmp_path):
    state, _, journal = _state(tmp_path)
    schema = {"type": "object", "required": ["isReal"],
              "properties": {"isReal": {"type": "boolean"}}}
    value = asyncio.run(state.agent("is it real?", schema=schema, label="v"))
    assert value["isReal"] is True
    journal.close()


def test_parallel_barrier(tmp_path):
    state, _, journal = _state(tmp_path)
    values = asyncio.run(state.parallel([
        lambda: state.agent("a"),
        lambda: state.agent("b"),
    ]))
    assert values == ["[mock] a", "[mock] b"]
    journal.close()


def test_pipeline_order(tmp_path):
    state, _, journal = _state(tmp_path)

    async def stage(value, item, idx):
        return value + f"-{item}"

    values = asyncio.run(state.pipeline(["x", "y"], stage))
    assert values == ["x-x", "y-y"]
    journal.close()


def test_agent_resume_uses_cache(tmp_path):
    from blh.workflow.journal import WorkflowJournal
    j1 = WorkflowJournal(RUN_ID, resume=False, store=tmp_path)
    state, _, _ = _state(tmp_path, journal=j1)
    asyncio.run(state.agent("same prompt", label="L"))
    j1.close()

    j2 = WorkflowJournal(RUN_ID, resume=True, store=tmp_path)
    state2, task2, _ = _state(tmp_path, journal=j2)
    value = asyncio.run(state2.agent("same prompt", label="L"))
    assert value == "[mock] same prompt"
    assert task2.usage["agents"] == 0  # 回放不重跑,不新增 agent 计数
    assert task2.progress[-1]["status"] == "cached"
    j2.close()


def test_budget_exceeded(tmp_path):
    state, _, journal = _state(tmp_path)
    state.budget = Budget(total=0)
    with pytest.raises(WorkflowInputError):
        asyncio.run(state.agent("hello"))
    journal.close()
