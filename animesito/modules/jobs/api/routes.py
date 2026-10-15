"""HTTP layer for the Jobs module, including the SSE progress stream."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from jfastframework.app import get_context
from jfastframework.plugins.builtin.database import DbSession

from modules.engine.public import ComfyError, comfy
from shared.enums import JobStatus

from ..models import JobEvent, JobRead
from ..repositories import JobRepository
from ..services import JobService, ProgressBus, to_event, to_read

router = APIRouter(prefix="/jobs", tags=["jobs"])

KEEPALIVE_SECONDS = 15.0


async def get_service(request: Request, session: DbSession) -> JobService:
    tenant_id = getattr(request.state, "tenant_id", None)
    return JobService(JobRepository(session, tenant_id=tenant_id))


def sse(event: JobEvent) -> str:
    return f"event: job\ndata: {event.model_dump_json()}\n\n"


async def stream_events(request: Request, bus: ProgressBus) -> AsyncIterator[str]:
    """Forward bus events; a comment every 15 s keeps proxies from closing it."""
    queue: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=1000)

    async def pump() -> None:
        async for event in bus.subscribe():
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    pumping = asyncio.create_task(pump())
    try:
        yield ": connected\n\n"
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
            except TimeoutError:
                yield ": ping\n\n"
                continue
            yield sse(event)
    finally:
        pumping.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pumping


@router.get("/events", summary="Server-sent events for every job change")
async def events(request: Request) -> StreamingResponse:
    bus: ProgressBus = get_context(request.app).require("jobs.bus")
    return StreamingResponse(
        stream_events(request, bus),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=list[JobRead], summary="Recent jobs, newest first")
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    service: JobService = Depends(get_service),
) -> list[JobRead]:
    return [to_read(job) for job in await service.recent(limit=limit)]


@router.get("/{job_id}", response_model=JobRead, summary="One job")
async def get_job(job_id: str, service: JobService = Depends(get_service)) -> JobRead:
    return to_read(await service.get(job_id))


@router.post("/{job_id}/cancel", response_model=JobRead, summary="Cancel a job")
async def cancel_job(
    job_id: str, request: Request, service: JobService = Depends(get_service)
) -> JobRead:
    before = JobStatus((await service.get(job_id)).status)
    job = await service.cancel(job_id)
    ctx = get_context(request.app)
    if job.comfy_prompt_id:
        client = comfy(ctx)
        # Cancelled already in our books; ComfyUI being away changes nothing.
        with contextlib.suppress(ComfyError):
            if before is JobStatus.RUNNING:
                await client.interrupt(job.comfy_prompt_id)
            else:
                await client.delete_queued([job.comfy_prompt_id])
    bus: ProgressBus = ctx.require("jobs.bus")
    await bus.publish(to_event(job))
    return to_read(job)
