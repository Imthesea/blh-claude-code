"""长期记忆存储:frontmatter 解析/生成、slug、路径校验、读写、索引。"""

import re
from pathlib import Path

import yaml

MEMORY_TYPES = ("user", "feedback", "project", "reference")
TEMPORARY_MEMORY_MARKERS = (
    "this session", "current session", "this turn", "current turn",
    "this task", "current task", "for now", "just this time", "today only",
    "本次会话", "当前会话", "这一轮", "当前轮次", "本次任务", "当前任务",
    "暂时", "今回だけ", "このセッション", "現在のタスク",
)
INDEX_NAME = "MEMORY.md"


class MemoryStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.index_path = self.directory / INDEX_NAME

    @staticmethod
    def parse_frontmatter(text: str) -> tuple[dict, str]:
        if not text.startswith("---\n"):
            return {}, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text
        try:
            metadata = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return {}, text
        if not isinstance(metadata, dict):
            return {}, text
        return metadata, parts[2].lstrip()

    @staticmethod
    def memory_slug(name: str) -> str:
        slug = re.sub(r"[^\w]+", "-", name.lower()).strip("-_")
        return slug or "memory"

    def memory_path(self, filename: str, allow_index: bool = False) -> Path:
        if Path(filename).name != filename:
            raise ValueError(f"Invalid memory filename: {filename}")
        if filename == self.index_path.name and not allow_index:
            raise ValueError("The memory index is not a memory record")
        path = (self.directory / filename).resolve()
        if not path.is_relative_to(self.directory.resolve()):
            raise ValueError(f"Memory path escapes the store: {filename}")
        return path
