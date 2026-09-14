from blh.cli.main import build_harness


def test_build_harness_wires_compactor_and_compact_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.compactor is not None
    assert harness.compactor.transcript_dir == tmp_path / ".transcripts"
    assert (harness.compactor.tool_results_dir
            == tmp_path / ".task_outputs" / "tool-results")
    names = [s["function"]["name"] for s in harness.tools.schemas()]
    assert "compact" in names


def test_build_harness_wires_planning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.todo_manager is not None
    names = [s["function"]["name"] for s in harness.tools.schemas()]
    for name in ("todo_write", "create_task", "update_task", "list_tasks",
                 "get_task", "claim_task", "complete_task"):
        assert name in names


def test_build_harness_wires_memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    harness = build_harness(workdir=str(tmp_path))
    assert harness.memory is not None
    assert harness.memory.store.directory == tmp_path / ".memory"
