"""cron 表达式解析与校验(五段式,零依赖)。"""

import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


def _cron_field_matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    if field.startswith("*/"):
        return value % int(field[2:]) == 0
    if "," in field:
        return any(_cron_field_matches(part.strip(), value)
                   for part in field.split(","))
    if "-" in field:
        start, end = field.split("-", 1)
        return int(start) <= value <= int(end)
    return value == int(field)


def cron_matches(cron_expr: str, moment: datetime) -> bool:
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, day, month, weekday = fields
    cron_weekday = (moment.weekday() + 1) % 7
    if not (
        _cron_field_matches(minute, moment.minute)
        and _cron_field_matches(hour, moment.hour)
        and _cron_field_matches(month, moment.month)
    ):
        return False
    day_matches = _cron_field_matches(day, moment.day)
    weekday_matches = _cron_field_matches(weekday, cron_weekday)
    if day == "*" and weekday == "*":
        return True
    if day == "*":
        return weekday_matches
    if weekday == "*":
        return day_matches
    return day_matches or weekday_matches


def _validate_cron_field(field: str, minimum: int, maximum: int) -> str | None:
    if field == "*":
        return None
    if field.startswith("*/"):
        step = field[2:]
        if not step.isdigit() or int(step) <= 0:
            return f"Invalid step: {field}"
        return None
    if "," in field:
        for part in field.split(","):
            error = _validate_cron_field(part.strip(), minimum, maximum)
            if error:
                return error
        return None
    if "-" in field:
        start, end = field.split("-", 1)
        if not start.isdigit() or not end.isdigit():
            return f"Invalid range: {field}"
        start_value, end_value = int(start), int(end)
        if start_value > end_value:
            return f"Range start is greater than end: {field}"
        if start_value < minimum or end_value > maximum:
            return f"Range {field} is outside [{minimum}-{maximum}]"
        return None
    if not field.isdigit():
        return f"Invalid field: {field}"
    value = int(field)
    if value < minimum or value > maximum:
        return f"Value {value} is outside [{minimum}-{maximum}]"
    return None


def validate_cron(cron_expr: str) -> str | None:
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return f"Expected 5 fields, got {len(fields)}"
    field_rules = [
        ("minute", 0, 59),
        ("hour", 0, 23),
        ("day-of-month", 1, 31),
        ("month", 1, 12),
        ("day-of-week", 0, 6),
    ]
    for field, (name, minimum, maximum) in zip(fields, field_rules):
        error = _validate_cron_field(field, minimum, maximum)
        if error:
            return f"{name}: {error}"
    return None


@dataclass
class CronJob:
    id: str
    cron: str
    prompt: str
    recurring: bool
    durable: bool
    pending_delivery: bool = False
    last_fired: str | None = None


class CronScheduler:
    def __init__(self, durable_path: Path):
        self.durable_path = Path(durable_path)
        self._jobs: dict[str, CronJob] = {}
        self._queue: list[CronJob] = []
        self._lock = threading.RLock()

    def _new_id(self) -> str:
        for _ in range(100):
            job_id = f"cron_{secrets.token_hex(4)}"
            if job_id not in self._jobs:
                return job_id
        raise RuntimeError("Could not allocate a cron job ID")

    def _save(self) -> None:
        payload = [asdict(job) for job in self._jobs.values() if job.durable]
        temporary = self.durable_path.with_name(
            f"{self.durable_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(temporary, self.durable_path)
        finally:
            temporary.unlink(missing_ok=True)

    def schedule(self, cron: str, prompt: str, recurring: bool = True,
                 durable: bool = True) -> CronJob:
        error = validate_cron(cron)
        if error:
            raise ValueError(error)
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Prompt cannot be empty")
        with self._lock:
            job = CronJob(id=self._new_id(), cron=cron, prompt=prompt,
                          recurring=recurring, durable=durable)
            self._jobs[job.id] = job
            try:
                if durable:
                    self._save()
            except Exception:
                self._jobs.pop(job.id, None)
                raise
        return job

    def list_jobs(self) -> list[CronJob]:
        with self._lock:
            return list(self._jobs.values())

    def cancel(self, job_id: str) -> str:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return f"Job {job_id} not found"
            previous_queue = list(self._queue)
            self._jobs.pop(job_id)
            self._queue[:] = [q for q in self._queue if q.id != job_id]
            try:
                if job.durable:
                    self._save()
            except Exception:
                self._jobs[job_id] = job
                self._queue[:] = previous_queue
                raise
        return f"Cancelled {job_id}"

    def _enqueue_due(self, job: CronJob, minute_marker: str) -> None:
        old_pending = job.pending_delivery
        old_last_fired = job.last_fired
        job.pending_delivery = True
        job.last_fired = minute_marker
        try:
            if job.durable:
                self._save()
        except Exception:
            job.pending_delivery = old_pending
            job.last_fired = old_last_fired
            raise
        self._queue.append(job)

    def poll_due(self, moment: datetime) -> None:
        minute_marker = moment.strftime("%Y-%m-%d %H:%M")
        with self._lock:
            for job in list(self._jobs.values()):
                if job.pending_delivery or job.last_fired == minute_marker:
                    continue
                if cron_matches(job.cron, moment):
                    self._enqueue_due(job, minute_marker)

    def consume_queue(self) -> list[CronJob]:
        with self._lock:
            jobs = list(self._queue)
            self._queue.clear()
        return jobs

    def acknowledge(self, jobs: list[CronJob]) -> None:
        durable_changed = False
        with self._lock:
            for delivered in jobs:
                current = self._jobs.get(delivered.id)
                if current is None:
                    continue
                if current.recurring:
                    current.pending_delivery = False
                    durable_changed = durable_changed or current.durable
                else:
                    durable_changed = durable_changed or current.durable
                    self._jobs.pop(current.id)
        if durable_changed:
            try:
                self._save()
            except Exception as error:  # noqa: BLE001 - 持久化失败仅记录,at-least-once 允许重复
                print(f"  [cron] acknowledgement persistence failed: {error}")

    def restore(self, jobs: list[CronJob]) -> None:
        with self._lock:
            queued_ids = {job.id for job in self._queue}
            for delivered in jobs:
                current = self._jobs.get(delivered.id)
                if current is None:
                    continue
                current.pending_delivery = True
                if current.id not in queued_ids:
                    self._queue.append(current)
                    queued_ids.add(current.id)

    def has_queue(self) -> bool:
        with self._lock:
            return bool(self._queue)

    def load(self) -> None:
        if not self.durable_path.exists():
            return
        try:
            payload = json.loads(self.durable_path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise TypeError("expected a JSON list")
        except (OSError, json.JSONDecodeError, TypeError) as error:
            print(f"  [cron] could not load {self.durable_path.name}: {error}")
            return
        with self._lock:
            for item in payload:
                try:
                    job = CronJob(**item)
                    error = validate_cron(job.cron)
                    if error:
                        raise ValueError(error)
                    if not job.id.startswith("cron_"):
                        raise ValueError("invalid job ID")
                    if not job.prompt.strip():
                        raise ValueError("prompt cannot be empty")
                except (TypeError, ValueError) as error:
                    print(f"  [cron] skipped invalid saved job: {error}")
                    continue
                self._jobs[job.id] = job
                if job.pending_delivery:
                    self._queue.append(job)
