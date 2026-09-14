"""jobs 工具注册:把 CronScheduler 封装为模型工具。"""

from ..tools.registry import Tool, ToolRegistry
from .cron import CronScheduler


def _scheduled(job) -> str:
    return f"Scheduled {job.id}: {job.cron} -> {job.prompt}"


def _listed(jobs) -> str:
    if not jobs:
        return "No cron jobs."
    lines = []
    for job in jobs:
        frequency = "recurring" if job.recurring else "one-shot"
        storage = "durable" if job.durable else "session"
        lines.append(
            f"{job.id}: {job.cron} -> {job.prompt[:60]} "
            f"[{frequency}, {storage}]")
    return "\n".join(lines)


def register_jobs_tools(registry: ToolRegistry, scheduler: CronScheduler) -> None:
    registry.register(Tool(
        name="schedule_cron",
        description="Schedule a prompt with a 5-field cron expression.",
        parameters={"type": "object", "properties": {
            "cron": {"type": "string"},
            "prompt": {"type": "string"},
            "recurring": {"type": "boolean"},
            "durable": {"type": "boolean"},
        }, "required": ["cron", "prompt"]},
        handler=lambda cron, prompt, recurring=True, durable=True: _scheduled(
            scheduler.schedule(cron, prompt, recurring, durable)),
    ))
    registry.register(Tool(
        name="list_crons",
        description="List scheduled cron jobs.",
        parameters={"type": "object", "properties": {}},
        handler=lambda: _listed(scheduler.list_jobs()),
    ))
    registry.register(Tool(
        name="cancel_cron",
        description="Cancel a cron job by ID.",
        parameters={"type": "object", "properties": {
            "job_id": {"type": "string"}}, "required": ["job_id"]},
        handler=lambda job_id: scheduler.cancel(job_id),
    ))
