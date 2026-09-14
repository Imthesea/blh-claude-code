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
