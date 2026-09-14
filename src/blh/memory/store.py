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

    @staticmethod
    def _normalized(value: str) -> str:
        return " ".join(value.lower().split())

    def should_store_memory(self, candidate: dict, existing: list[dict]) -> bool:
        if not isinstance(candidate, dict):
            return False
        if candidate.get("scope") != "persistent":
            return False
        if candidate.get("type") not in MEMORY_TYPES:
            return False

        name = str(candidate.get("name", "")).strip()
        description = str(candidate.get("description", "")).strip()
        body = str(candidate.get("body", "")).strip()
        if not name or not description or not body:
            return False

        candidate_text = self._normalized(f"{name}\n{description}\n{body}")
        if any(marker in candidate_text for marker in TEMPORARY_MEMORY_MARKERS):
            return False

        slug = self.memory_slug(name)
        normalized_description = self._normalized(description)
        normalized_body = self._normalized(body)
        for memory in existing:
            if self.memory_slug(str(memory.get("name", ""))) == slug:
                return False
            if self._normalized(str(memory.get("description", ""))) == normalized_description:
                return False
            if self._normalized(str(memory.get("body", ""))) == normalized_body:
                return False
        return True

    def memory_document(self, name: str, mem_type: str, description: str,
                        body: str) -> str:
        metadata = yaml.safe_dump(
            {"name": name, "description": description, "type": mem_type},
            sort_keys=False, allow_unicode=True,
        ).strip()
        return f"---\n{metadata}\n---\n\n{body.strip()}\n"

    def write_memory_file(self, name, mem_type, description, body) -> Path:
        if not name.strip():
            raise ValueError("Memory name cannot be empty")
        if mem_type not in MEMORY_TYPES:
            raise ValueError(f"Unknown memory type: {mem_type}")
        if not description.strip() or not body.strip():
            raise ValueError("Memory description and body cannot be empty")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.memory_path(f"{self.memory_slug(name)}.md")
        path.write_text(
            self.memory_document(name, mem_type, description, body),
            encoding="utf-8",
        )
        self.rebuild_memory_index()
        return path

    def rebuild_memory_index(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        lines = []
        for path in sorted(self.directory.glob("*.md")):
            if path.name == self.index_path.name:
                continue
            try:
                path = self.memory_path(path.name)
            except ValueError:
                continue
            metadata, body = self.parse_frontmatter(path.read_text(encoding="utf-8"))
            name = " ".join(str(metadata.get("name") or path.stem).split())
            first_line = next((line for line in body.splitlines() if line.strip()), "")
            description = " ".join(
                str(metadata.get("description") or first_line).split())
            lines.append(f"- [{name}]({path.name}) - {description}")
        self.memory_path(self.index_path.name, allow_index=True).write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def read_memory_index(self) -> str:
        try:
            path = self.memory_path(self.index_path.name, allow_index=True)
        except ValueError:
            return ""
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    def read_memory_file(self, filename: str) -> str | None:
        try:
            path = self.memory_path(filename)
        except ValueError:
            return None
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def list_memory_files(self) -> list[dict]:
        records = []
        if not self.directory.exists():
            return records
        for path in sorted(self.directory.glob("*.md")):
            if path.name == self.index_path.name:
                continue
            try:
                path = self.memory_path(path.name)
            except ValueError:
                continue
            metadata, body = self.parse_frontmatter(path.read_text(encoding="utf-8"))
            records.append({
                "filename": path.name,
                "name": str(metadata.get("name") or path.stem),
                "description": str(metadata.get("description") or ""),
                "type": str(metadata.get("type") or "project"),
                "body": body.strip(),
            })
        return records
