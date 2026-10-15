"""The ``jobs`` plugin: the progress bus and the ComfyUI dispatcher.

Both the API and ``jfast worker`` load it; the dispatcher's Redis lease makes
sure only one of them feeds ComfyUI at a time.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from pydantic_settings import SettingsConfigDict

from jfastframework.plugins.base import Plugin, PluginMeta, PluginSettings
from jfastframework.queues.base import Job as QueueJob
from jfastframework.queues.base import QueueBackend

from modules.engine.public import comfy

from .services import Dispatcher, RedisBus, RedisLock

if TYPE_CHECKING:
    from jfastframework.context import AppContext


class JobsSettings(PluginSettings):
    model_config = SettingsConfigDict(env_prefix="JFAST_JOBS_", env_file=".env", extra="ignore")

    dispatcher: bool = True
    tick_seconds: float = 1.0
    lock_ttl: int = 15


class JobsPlugin(Plugin):
    meta = PluginMeta(
        name="jobs",
        version="0.1.0",
        description="Job progress bus and the ComfyUI dispatcher.",
        requires=("database", "cache", "queue", "storage", "comfy"),
        provides=("jobs.bus",),
    )
    Settings = JobsSettings

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._task: asyncio.Task[None] | None = None

    def register(self, ctx: AppContext) -> None:
        ctx.provide("jobs.bus", RedisBus(ctx.require("cache.client")))

    async def startup(self, ctx: AppContext) -> None:
        settings: JobsSettings = self.settings
        if not settings.dispatcher:
            return
        queue: QueueBackend = ctx.require("queue")

        async def enqueue_ingest(job_id: str) -> None:
            await queue.enqueue(QueueJob(task="jobs.ingest", payload={"job_id": job_id}))

        dispatcher = Dispatcher(
            sessionmaker=ctx.require("db.sessionmaker"),
            comfy=comfy(ctx),
            bus=ctx.require("jobs.bus"),
            enqueue_ingest=enqueue_ingest,
            disk=ctx.require("storage").disk(),
            before_submit=list(ctx.get("jobs.before_submit", [])),
            tick=settings.tick_seconds,
            lock=RedisLock(ctx.require("cache.client"), ttl=settings.lock_ttl),
        )
        self._task = asyncio.create_task(dispatcher.run(), name="animesito-dispatcher")

    async def shutdown(self, ctx: AppContext) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
