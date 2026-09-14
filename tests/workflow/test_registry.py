from blh.workflow.registry import WORKFLOWS


def test_registry_contains_sample():
    assert "review-changes" in WORKFLOWS
    meta, fn = WORKFLOWS["review-changes"]
    assert meta["name"] == "review-changes"
    assert callable(fn)
