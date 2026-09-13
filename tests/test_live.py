import os

import pytest

from blh.cli.main import build_harness
from blh.core.loop import last_assistant_text


@pytest.mark.live
def test_live_single_turn(tmp_path):
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("no API key")
    harness = build_harness(workdir=str(tmp_path))
    messages = harness.new_session()
    harness.run_turn(messages, "Reply with exactly: pong")
    assert "pong" in last_assistant_text(messages).lower()
