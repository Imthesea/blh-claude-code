"""技能按需加载:启动注入目录,load_skill 才读完整 SKILL.md。"""

from pathlib import Path

import yaml


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, dict[str, str]] = {}
        self.scan()

    @staticmethod
    def parse_frontmatter(text: str) -> tuple[dict, str]:
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != "---":
            return {}, text
        closing = next((i for i, line in enumerate(lines[1:], start=1)
                        if line.rstrip("\r\n") == "---"), None)
        if closing is None:
            return {}, text
        frontmatter = "".join(lines[1:closing])
        body = "".join(lines[closing + 1:]).strip()
        try:
            meta = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError:
            meta = {}
        return (meta if isinstance(meta, dict) else {}), body

    def scan(self):
        self.skills.clear()
        if not self.skills_dir.exists():
            return
        root = self.skills_dir.resolve()
        for manifest in sorted(self.skills_dir.glob("*/SKILL.md")):
            if not manifest.is_file() or not manifest.resolve().is_relative_to(root):
                continue
            content = manifest.read_text(encoding="utf-8")
            meta, body = self.parse_frontmatter(content)
            name = (meta.get("name") or "").strip() or manifest.parent.name
            description = (meta.get("description") or "").strip() or body.split("\n", 1)[0]
            description = " ".join(str(description).lstrip("# ").split())
            self.skills[name] = {"name": name, "description": description,
                                 "content": content}

    def catalog(self) -> str:
        if not self.skills:
            return "(no skills found)"
        return "\n".join(f"- {s['name']}: {s['description']}"
                         for s in self.skills.values())

    def load(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill:
            return skill["content"]
        available = ", ".join(self.skills) or "none"
        return f"Error: Unknown skill '{name}'. Available: {available}"
