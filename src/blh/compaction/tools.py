from ..tools.registry import Tool, ToolRegistry


def register_compact_tool(registry: ToolRegistry) -> None:
    """注册 compact 工具;实际执行由 agent loop 拦截(批次闭合后压缩)。"""
    registry.register(Tool(
        name="compact",
        description="Summarize earlier conversation to free context space.",
        parameters={"type": "object", "properties": {}},
        handler=lambda: "Compaction requested after this tool batch.",
    ))
