"""JobsRuntime:组合后台任务与 cron 调度,管理线程生命周期与 agent 互斥锁。"""

import threading
from datetime import datetime

from .background import BackgroundManager
from .cron import CronScheduler


class JobsRuntime:
    def __init__(self, background: BackgroundManager, cron: CronScheduler):
        self.background = background
        self.cron = cron
        self.agent_lock = threading.Lock()
        self._cron_turn = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._started = False
        self._lock = threading.Lock()

    def set_cron_turn(self, callback) -> None:
        self._cron_turn = callback

    def inject_background_results(self, messages: list[dict]) -> int:
        notifications = self.background.collect()
        for notification in notifications:
            messages.append({"role": "user", "content": notification})
        return len(notifications)

    def consume_and_inject_cron(self, messages: list[dict]) -> list:
        jobs = self.cron.consume_queue()
        for job in jobs:
            messages.append({"role": "user",
                             "content": f"[Scheduled] {job.prompt}"})
        return jobs

    def start_background(self, command: str) -> str:
        task_id = self.background.start(command)
        return (f"[Background task {task_id} started] "
                "The result will be collected on a later turn.")

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self.cron.load()
            self._stop.clear()
            self._threads = [
                threading.Thread(target=self._scheduler_loop,
                                 name="cron-scheduler", daemon=True),
                threading.Thread(target=self._queue_processor_loop,
                                 name="cron-queue-processor", daemon=True),
            ]
            for thread in self._threads:
                thread.start()
            self._started = True

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            self._stop.set()
            for thread in self._threads:
                thread.join(timeout=1)
            self._threads = []
            self._started = False

    def _scheduler_loop(self) -> None:
        while not self._stop.wait(1.0):
            self.cron.poll_due(datetime.now())  # noqa: DTZ005 - cron 按本地时间触发

    def _queue_processor_loop(self) -> None:
        while not self._stop.wait(0.2):
            if not self.cron.has_queue() or not self.agent_lock.acquire(blocking=False):
                continue
            try:
                if self.cron.has_queue() and self._cron_turn is not None:
                    self._cron_turn()
            finally:
                self.agent_lock.release()
