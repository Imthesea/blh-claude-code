import json

from .hooks import POST_TOOL_USE, PRE_TOOL_USE


def agent_loop(harness, messages: list[dict]) -> None:
    while True:
        assistant = harness.provider.chat(messages, harness.tools.schemas())
        messages.append(assistant)

        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            return

        for call in tool_calls:
            name = call["function"]["name"]
            arguments = call["function"].get("arguments") or "{}"
            call_id = call.get("id", "")
            event = {"name": name, "input": _parse_args(arguments), "id": call_id}

            blocked = harness.hooks.first_block(PRE_TOOL_USE, event)
            if blocked is not None:
                result = blocked
            else:
                result = harness.tools.dispatch(name, arguments)
                harness.hooks.trigger(POST_TOOL_USE, event, result)

            messages.append({"role": "tool",
                             "tool_call_id": call_id,
                             "content": result})


def last_assistant_text(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg["role"] == "assistant" and msg.get("content"):
            return msg["content"]
    return ""


def _parse_args(arguments: str) -> dict:
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
