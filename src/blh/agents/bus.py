"""MessageBus:线程安全文件收件箱,破坏性读。"""

import json
import re
import threading
import time
from pathlib import Path

VALID_AGENT_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_valid_agent_name(name: str) -> bool:
    return bool(VALID_AGENT_NAME.fullmatch(name))


class MessageBus:
    def __init__(self, mailbox_dir: Path):
        self.mailbox_dir = Path(mailbox_dir)
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)

    def _path(self, agent: str) -> Path:
        if not is_valid_agent_name(agent):
            raise ValueError(f"Invalid mailbox recipient: {agent!r}")
        path = (self.mailbox_dir / f"{agent}.jsonl").resolve()
        root = self.mailbox_dir.resolve()
        if path.parent != root:
            raise ValueError(f"Mailbox path escapes directory: {agent!r}")
        return path

    def _read_unlocked(self, agent: str) -> list[dict]:
        inbox = self._path(agent)
        if not inbox.exists():
            return []
        msgs = [json.loads(line) for line in
                inbox.read_text(encoding="utf-8").splitlines() if line.strip()]
        inbox.unlink()
        return msgs

    def send(self, from_agent, to_agent, content, msg_type="message", metadata=None):
        msg = {"from": from_agent, "to": to_agent, "content": content,
               "type": msg_type, "ts": time.time(), "metadata": metadata or {}}
        with self._changed:
            self.mailbox_dir.mkdir(parents=True, exist_ok=True)
            with self._path(to_agent).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(msg, ensure_ascii=True) + "\n")
            self._changed.notify_all()

    def read_inbox(self, agent):
        with self._lock:
            return self._read_unlocked(agent)

    def peek(self, agent):
        with self._lock:
            inbox = self._path(agent)
            return inbox.exists() and inbox.stat().st_size > 0

    def wait_for_messages(self, agent, timeout=None):
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._changed:
            while not self.peek(agent):
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return []
                self._changed.wait(remaining)
            return self._read_unlocked(agent)
