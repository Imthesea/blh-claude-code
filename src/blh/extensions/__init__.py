"""扩展能力:skills 按需加载 + MCP 客户端。"""


class Extensions:
    def __init__(self, skills, mcp):
        self.skills = skills
        self.mcp = mcp

    def system_prompt_section(self) -> str:
        parts = []
        catalog = self.skills.catalog()
        if catalog != "(no skills found)":
            parts.append("Skills available:\n" + catalog)
        section = self.mcp.system_prompt_section()
        if section:
            parts.append(section)
        return "\n\n".join(parts)
