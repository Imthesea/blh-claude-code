import pytest

from blh.workflow.journal import WorkflowJournal
from blh.workflow.schema import MISS, WorkflowInputError

RUN_ID = "wf_demo_0000000000000001"


def test_key_is_deterministic(tmp_path):
    j = WorkflowJournal(RUN_ID, resume=False, store=tmp_path)
    assert j.key("agent", "l", "p", None) == j.key("agent", "l", "p", None)
    j.close()


def test_record_and_resume(tmp_path):
    store = tmp_path / ".runtime"
    j = WorkflowJournal(RUN_ID, resume=False, store=store)
    key = j.key("agent", "label", "prompt", None)
    j.record(key, {"v": 1})
    j.close()
    # 同参数 key 应稳定
    j2 = WorkflowJournal(RUN_ID, resume=True, store=store)
    assert j2.cached(key) == {"v": 1}
    j2.close()


def test_cached_miss(tmp_path):
    j = WorkflowJournal(RUN_ID, resume=False, store=tmp_path)
    assert j.cached("agent-0000000000") is MISS
    j.close()


def test_resume_missing_journal_raises(tmp_path):
    with pytest.raises(WorkflowInputError):
        WorkflowJournal(RUN_ID, resume=True, store=tmp_path)


def test_invalid_record_raises(tmp_path):
    store = tmp_path / ".runtime"
    store.mkdir()
    (store / f"{RUN_ID}.journal.jsonl").write_text("not json\n", encoding="utf-8")
    with pytest.raises(WorkflowInputError):
        WorkflowJournal(RUN_ID, resume=True, store=store)
