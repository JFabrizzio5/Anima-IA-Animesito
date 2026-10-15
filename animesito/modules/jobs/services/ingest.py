"""Move a finished job's files from ComfyUI's output folder into the gallery.

Runs as the ``jobs.ingest`` queue task, so a failure is retried by the worker.
Guarded by status, not by an inbox claim: only an ``ingesting`` job is
ingested, and ``done`` is a compare-and-set, so a redelivery after success is
a no-op. The event is published after the commit, so the browser never asks
for a gallery row that is not visible yet.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from modules.engine.public import ComfyClient
from modules.gallery.public import NewMedia, save_media
from shared.enums import JobStatus, MediaSource

from ..repositories import JobRepository
from .dispatcher import output_from_dict
from .job_service import JobService, to_event
from .progress_bus import ProgressBus


async def ingest_job(
    *,
    sessionmaker: Callable[[], Any],
    comfy: ComfyClient,
    disk: Any,
    bus: ProgressBus,
    job_id: str,
) -> list[int]:
    result_ids: list[int] = []
    async with sessionmaker() as session, session.begin():
        service = JobService(JobRepository(session))
        job = await service.repository.get(job_id)
        if job is None or job.status != JobStatus.INGESTING.value:
            return []
        params: dict[str, Any] = job.params or {}
        for raw in job.outputs or []:
            file = output_from_dict(raw)
            data = await comfy.view(file)
            summary = await save_media(
                session,
                disk,
                tenant_id=job.tenant_id,
                media=NewMedia(
                    data=data,
                    filename=file.filename,
                    kind=file.media,
                    source=MediaSource.GENERATED,
                    job_id=job.id,
                    prompt=str(params.get("prompt", "")),
                    negative=str(params.get("negative", "")),
                    model=params.get("model"),
                    seed=params.get("seed"),
                    adult=bool(params.get("adult", False)),
                    params=params,
                ),
            )
            result_ids.append(summary.id)
        await service.done(job.id, result_ids)

    async with sessionmaker() as session:
        finished = await JobRepository(session).get(job_id)
        if finished is not None:
            await bus.publish(to_event(finished))
    return result_ids
