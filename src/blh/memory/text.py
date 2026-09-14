"""memory 共享文本/JSON 解析原语。"""

import json


def message_text(message: dict) -> str:
    content = message.get("content", "")
    return content if isinstance(content, str) else ""


def extract_json_array(text: str) -> list:
    decoder = json.JSONDecoder()
    for position, character in enumerate(text):
        if character != "[":
            continue
        try:
            value, _ = decoder.raw_decode(text[position:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return value
    return []
