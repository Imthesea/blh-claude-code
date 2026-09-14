"""goal transcript:按 OpenAI 消息格式渲染会话文本。"""


def _plain_content(message: dict) -> str:
    role = message.get("role", "unknown")
    content = message.get("content")
    if role == "assistant":
        parts = []
        if content:
            parts.append(str(content))
        for call in message.get("tool_calls") or []:
            fn = call.get("function", {}) or {}
            parts.append(f"[tool_call {fn.get('name', '')} {fn.get('arguments', '{}')}]")
        return "\n".join(parts)
    if role == "tool":
        return f"[tool_result {content}]"
    return str(content or "")


def transcript_text(messages, max_characters=24000):
    rendered = [
        f"{message.get('role', 'unknown').upper()}:\n{_plain_content(message)}"
        for message in messages
    ]
    selected = []
    size = 0
    for item in reversed(rendered):
        item_size = len(item) + 2
        if not selected and item_size > max_characters:
            marker = "\n...[middle omitted]...\n"
            available = max(0, max_characters - len(marker))
            if available == 0:
                selected.append(marker[:max_characters])
            else:
                head = available * 3 // 4
                tail = available - head
                selected.append(item[:head] + marker + item[-tail:])
            break
        if selected and size + item_size > max_characters:
            break
        selected.append(item)
        size += item_size
    return "\n\n".join(reversed(selected))
