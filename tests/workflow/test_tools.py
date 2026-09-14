from blh.tools.registry import ToolRegistry
from blh.workflow.registry import WORKFLOWS
from blh.workflow.runtime import MockWorkflowRunner
from blh.workflow.tools import register_workflow_tools


def test_registers_run_workflow(tmp_path):
    registry = ToolRegistry()
    register_workflow_tools(registry, store=tmp_path,
                            runner_factory=MockWorkflowRunner,
                            workflows=WORKFLOWS)
    names = [s["function"]["name"] for s in registry.schemas()]
    assert "run_workflow" in names
