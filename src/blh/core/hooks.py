from collections import defaultdict
from collections.abc import Callable

USER_PROMPT_SUBMIT = "UserPromptSubmit"
PRE_TOOL_USE = "PreToolUse"
POST_TOOL_USE = "PostToolUse"
STOP = "Stop"


class HookBus:
    def __init__(self):
        self._hooks: dict[str, list[Callable]] = defaultdict(list)

    def register(self, event: str, callback: Callable) -> None:
        self._hooks[event].append(callback)

    def trigger(self, event: str, *args, **kwargs) -> list:
        return [cb(*args, **kwargs) for cb in self._hooks.get(event, [])]

    def first_block(self, event: str, *args, **kwargs):
        """按注册顺序调用 hook,首个非 None 返回值即拦截信号;全 None 返回 None 放行。

        hook 异常向上传播、不兜底(fail-closed):PreToolUse 拦截 hook 崩溃时
        宁可中断会话也不静默放行工具执行。
        """
        for cb in self._hooks.get(event, []):
            result = cb(*args, **kwargs)
            if result is not None:
                return result
        return None
