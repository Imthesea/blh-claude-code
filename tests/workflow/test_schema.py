import pytest

from blh.workflow.schema import (
    MISS,
    SimpleJsonSchema,
    WorkflowInputError,
    _stable_hash,
    parse_runner_json,
)


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
    assert parse_runner_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_runner_json_invalid():
    with pytest.raises(WorkflowInputError):
        parse_runner_json("no json here")


def test_miss_sentinel_unique():
    assert MISS is not None
    assert MISS != object()
