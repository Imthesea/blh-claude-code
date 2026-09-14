import json

from ..providers.openai import is_prompt_too_long
from .hooks import POST_TOOL_USE, PRE_TOOL_USE

MAX_REACTIVE_RETRIES = 1


def agent_loop(harness, messages: list[dict], active_request: str = "") -> None:
    system_message = (messages[0] if messages
                      else {"role": "system",
                            "content": harness.system_prompt()})
    reactive_retries = 0
    while True:
        compactor = harness.compactor
        if compactor is not None:
            messages[:] = compactor.prepare(messages, active_request)
            _restore_system(messages, system_message)
        try:
            assistant = harness.provider.chat(messages, harness.tools.schemas())
            reactive_retries = 0
        except Exception as error:
            if (compactor is not None and is_prompt_too_long(error)
                    and reactive_retries < MAX_REACTIVE_RETRIES):
                print("[reactive compact]")
                messages[:] = compactor.reactive_compact(
                    messages, active_request)
                _restore_system(messages, system_message)
                reactive_retries += 1
                continue
            raise
        messages.append(assistant)

        tool_calls = assistant.get("tool_calls") or []
        if not tool_calls:
            return

        compact_requested = False
        used_todo = False
        for call in tool_calls:
            name = call["function"]["name"]
            arguments = call["function"].get("arguments") or "{}"
            call_id = call.get("id", "")
            event = {"name": name, "input": _parse_args(arguments), "id": call_id}

            if compactor is not None and name == "compact":
                # compact 由 loop 拦截:先闭合本批次,再压缩,不走 dispatch/hooks
                result = "Compaction requested after this tool batch."
                compact_requested = True
            else:
                blocked = harness.hooks.first_block(PRE_TOOL_USE, event)
                if blocked is not None:
                    result = blocked
                else:
                    result = harness.tools.dispatch(name, arguments)
                    harness.hooks.trigger(POST_TOOL_USE, event, result)
                if name == "todo_write":
                    used_todo = True

            messages.append({"role": "tool",
                             "tool_call_id": call_id,
                             "content": result})

        todo_manager = harness.todo_manager
        if todo_manager is not None:
            reminder = todo_manager.note_round(used_todo)
            if reminder and messages and messages[-1]["role"] == "tool":
                messages[-1]["content"] += reminder

        if compact_requested:
            messages[:] = compactor.compact_history(messages, active_request)
            _restore_system(messages, system_message)


def _restore_system(messages: list[dict], system_message: dict) -> None:
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, system_message)


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
