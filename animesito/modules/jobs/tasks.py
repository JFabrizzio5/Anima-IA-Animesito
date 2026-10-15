"""Background work the Jobs module owns."""

from __future__ import annotations

from typing import Any

from jfastframework.tasks import TaskContext, task

from modules.engine.public import comfy

from .services import ingest_job


@task("jobs.ingest")
async def ingest(payload: dict[str, Any], ctx: TaskContext) -> None:
    """Copy a finished job's outputs into the gallery (status-guarded, retry-safe)."""
    await ingest_job(
        sessionmaker=ctx.require("db.sessionmaker"),
        comfy=comfy(ctx),
        disk=ctx.require("storage").disk(),
        bus=ctx.require("jobs.bus"),
        job_id=str(payload["job_id"]),
    )
