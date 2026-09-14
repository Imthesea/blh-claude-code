from blh.extensions.mcp import MCPRegistry
from blh.extensions.skills import SkillLoader
from blh.extensions.tools import register_extension_tools
from blh.tools.registry import ToolRegistry


def test_registers_load_skill_and_connect_mcp(tmp_path):
    registry = ToolRegistry()
    skills = SkillLoader(tmp_path / "skills")
    mcp = MCPRegistry(registry, ".")
    register_extension_tools(registry, skills, mcp)
    names = [s["function"]["name"] for s in registry.schemas()]
    assert "load_skill" in names
    assert "connect_mcp" in names
