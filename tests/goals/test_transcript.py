from blh.goals.transcript import transcript_text


def test_plain_assistant_with_tool_calls():
    messages = [
        {"role": "assistant", "content": None,
         "tool_calls": [{"function": {"name": "bash",
                                      "arguments": "{\"command\": \"ls\"}"}}]},
    ]
    text = transcript_text(messages)
    assert "tool_call" in text
    assert "bash" in text


def test_tool_result_rendered():
    messages = [{"role": "tool", "content": "exit_code=0"}]
    assert "tool_result" in transcript_text(messages)


def test_truncates_oversized_newest_drops_older():
    # 最新一条超长:只截该条(带 omitted 标记),更旧消息被丢弃
    messages = [{"role": "user", "content": "first"},
                {"role": "user", "content": "second"},
                {"role": "user", "content": "x" * 5000}]
    text = transcript_text(messages, max_characters=100)
    assert "omitted" in text
    assert "first" not in text


def test_keeps_recent_complete_messages():
    messages = [{"role": "user", "content": "first"},
                {"role": "user", "content": "second"}]
    text = transcript_text(messages, max_characters=1000)
    assert "USER:\nfirst" in text
    assert "USER:\nsecond" in text
