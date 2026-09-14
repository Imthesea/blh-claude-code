import threading
import time

import pytest

from blh.agents.bus import MessageBus, is_valid_agent_name


def make_bus(tmp_path):
    return MessageBus(tmp_path / ".mailboxes")


def test_send_and_read_is_destructive(tmp_path):
    bus = make_bus(tmp_path)
    bus.send("alice", "bob", "hi", "message")
    msgs = bus.read_inbox("bob")
    assert len(msgs) == 1
    assert msgs[0]["from"] == "alice"
    assert msgs[0]["content"] == "hi"
    assert bus.read_inbox("bob") == []


def test_send_rejects_invalid_recipient(tmp_path):
    bus = make_bus(tmp_path)
    with pytest.raises(ValueError):
        bus.send("alice", "../etc", "x")


def test_is_valid_agent_name():
    assert is_valid_agent_name("alice-1")
    assert not is_valid_agent_name("../x")
    assert not is_valid_agent_name("a b")


def test_wait_for_messages_wakes_on_send(tmp_path):
    bus = make_bus(tmp_path)
    result = []

    def waiter():
        result.append(bus.wait_for_messages("bob", timeout=2.0))

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.05)
    bus.send("alice", "bob", "hello")
    thread.join(timeout=3)
    assert len(result) == 1 and result[0][0]["content"] == "hello"


def test_wait_for_messages_times_out(tmp_path):
    bus = make_bus(tmp_path)
    assert bus.wait_for_messages("bob", timeout=0.05) == []
