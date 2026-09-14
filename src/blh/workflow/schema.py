"""workflow 基础:稳定 hash、最小 JSON Schema 校验、JSON 提取。"""

import hashlib
import json

MISS = object()


class WorkflowInputError(Exception):
    """非法 workflow / 元数据 / schema 输入。"""


def _stable_hash(s: str) -> int:
    """跨进程稳定 hash(Python 内置 hash 每进程加盐,会破坏 resume key)。"""
    return int(hashlib.sha256(s.encode()).hexdigest(), 16)


class SimpleJsonSchema:
    """极简校验器:object/array/string/boolean/number + required/enum。"""

    def __init__(self, schema):
        self.schema = schema

    def validate(self, value, schema=None):
        schema = self.schema if schema is None else schema
        if "enum" in schema and value not in schema["enum"]:
            return False, f"expected one of {schema['enum']}"
        t = schema.get("type")
        if t == "object":
            if not isinstance(value, dict):
                return False, "expected object"
            for key in schema.get("required", []):
                if key not in value:
                    return False, f"missing required key '{key}'"
            for key, sub in schema.get("properties", {}).items():
                if key in value:
                    ok, err = self.validate(value[key], sub)
                    if not ok:
                        return False, f"{key}: {err}"
            return True, None
        if t == "array":
            if not isinstance(value, list):
                return False, "expected array"
            items = schema.get("items")
            if items:
                for i, el in enumerate(value):
                    ok, err = self.validate(el, items)
                    if not ok:
                        return False, f"[{i}]: {err}"
            return True, None
        if t == "string":
            return (isinstance(value, str),
                    None if isinstance(value, str) else "expected string")
        if t == "boolean":
            return (isinstance(value, bool),
                    None if isinstance(value, bool) else "expected boolean")
        if t in ("number", "integer"):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            return (ok, None if ok else "expected number")
        return True, None


def parse_runner_json(text: str):
    """提取 agent 返回的 JSON:支持围栏代码块,失败时扫首个 '{' 起的对象。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:] if lines else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for position, character in enumerate(stripped):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(stripped[position:])
            except json.JSONDecodeError:
                continue
            return value
        raise WorkflowInputError("workflow agent returned invalid JSON")
