from blh.workflow.registry import WORKFLOWS
from blh.workflow.runtime import MockWorkflowRunner
from blh.workflow.tool import run_workflow_sync


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
