"""Feeds ComfyUI one job at a time and follows it to the end.

Why not one queue task per render: the framework queue cancels a handler at
80% of its visibility timeout and never extends the claim, and a video render
outlives any sane timeout. ComfyUI already serialises execution, so the GPU
"queue" is ComfyUI's; this loop only decides *when* to hand it the next prompt
(one at a time, so cancelling, VRAM hand-offs and priorities stay ours) and
translates its WebSocket events into job transitions.

One dispatcher per deployment: it holds a Redis lock while it runs, so the API
and the worker can both start one and exactly one dispatches.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from modules.engine.public import (
    ComfyClient,
    ComfyEvent,
    ComfyRejected,
    ComfyUnavailable,
    OutputFile,
    WorkflowError,
    set_inputs,
)
from shared.enums import JobStatus, MediaKind

from ..models import Job
from ..repositories import JobRepository
from .job_service import JobService, to_event
from .progress_bus import ProgressBus

logger = logging.getLogger("animesito.dispatcher")

Hook = Callable[[], Awaitable[None]]

#: An ingest that has not finished in this long lost its queue job.
STALE_INGEST = timedelta(minutes=15)
#: After the final event, how long to keep asking for a history that is late.
HISTORY_RETRIES = 5
HISTORY_RETRY_SECONDS = 0.4


class LockLost(RuntimeError):
    pass


class RedisLock:
    """A lease: set-if-absent with a TTL, renewed while the holder is alive."""

    def __init__(self, client: Any, key: str = "animesito:dispatcher", ttl: int = 15) -> None:
        self._client = client
        self._key = key
        self.ttl = ttl
        self.owner = uuid.uuid4().hex

    async def acquire(self) -> bool:
        if await self._client.set(self._key, self.owner, nx=True, ex=self.ttl):
            return True
        return await self.renew()

    async def renew(self) -> bool:
        if await self._client.get(self._key) == self.owner:
            await self._client.expire(self._key, self.ttl)
            return True
        return False

    async def release(self) -> None:
        if await self._client.get(self._key) == self.owner:
            await self._client.delete(self._key)


def describe_rejection(exc: ComfyRejected) -> str:
    details: list[str] = []
    for node, info in exc.node_errors.items():
        for error in (info or {}).get("errors", []) if isinstance(info, dict) else []:
            message = error.get("details") or error.get("message") or ""
            details.append(f"nodo {node} ({info.get('class_type', '?')}): {message}")
    return "; ".join([str(exc), *details])


def output_to_dict(file: OutputFile) -> dict[str, Any]:
    return {
        "filename": file.filename,
        "subfolder": file.subfolder,
        "type": file.type,
        "media": file.media.value,
    }


def output_from_dict(raw: dict[str, Any]) -> OutputFile:
    return OutputFile(
        filename=str(raw["filename"]),
        subfolder=str(raw.get("subfolder", "")),
        type=str(raw.get("type", "output")),
        media=MediaKind(raw.get("media", MediaKind.IMAGE.value)),
    )


class Dispatcher:
    def __init__(
        self,
        *,
        sessionmaker: Callable[[], Any],
        comfy: ComfyClient,
        bus: ProgressBus,
        enqueue_ingest: Callable[[str], Awaitable[Any]],
        disk: Any = None,
        before_submit: Sequence[Hook] = (),
        tick: float = 1.0,
        lock: RedisLock | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._comfy = comfy
        self._bus = bus
        self._enqueue_ingest = enqueue_ingest
        self._disk = disk
        self._before_submit = list(before_submit)
        self._tick = tick
        self._lock = lock
        # prompt_id -> job_id for prompts submitted by this process, filled the
        # instant ComfyUI answers: its first events can beat our own commit.
        self._inflight: dict[str, str] = {}

    # -- plumbing ------------------------------------------------------------

    @asynccontextmanager
    async def _service(self) -> Any:
        async with self._sessionmaker() as session, session.begin():
            yield JobService(JobRepository(session))

    async def _publish(self, job_id: str) -> None:
        async with self._sessionmaker() as session:
            job = await JobRepository(session).get(job_id)
            if job is not None:
                await self._bus.publish(to_event(job))

    async def _job_for(self, prompt_id: str) -> str | None:
        if prompt_id in self._inflight:
            return self._inflight[prompt_id]
        async with self._sessionmaker() as session:
            job = await JobRepository(session).by_prompt_id(prompt_id)
            return job.id if job is not None else None

    # -- main loop -----------------------------------------------------------

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        backoff = 1.0
        try:
            while True:
                if self._lock is not None and not await self._lock.acquire():
                    await asyncio.sleep(max(self._lock.ttl / 3, 1.0))
                    continue
                started = loop.time()
                try:
                    await self.reconcile()
                    await self._serve()
                except* ComfyUnavailable as group:
                    logger.warning("ComfyUI unavailable: %s", group.exceptions[0])
                except* LockLost:
                    logger.warning("dispatcher lock lost; standing by")
                except* Exception:
                    logger.exception("dispatcher loop failed; restarting")
                # A connection that held for a minute was healthy: start over.
                if loop.time() - started > 60:
                    backoff = 1.0
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
        finally:
            if self._lock is not None:
                with contextlib.suppress(Exception):
                    await self._lock.release()

    async def _serve(self) -> None:
        async with asyncio.TaskGroup() as group:
            group.create_task(self._listen())
            group.create_task(self._pump())

    async def _listen(self) -> None:
        async for event in self._comfy.events():
            await self.handle(event)
        raise ComfyUnavailable("ComfyUI closed the WebSocket")

    async def _pump(self) -> None:
        while True:
            if self._lock is not None and not await self._lock.renew():
                raise LockLost
            submitted = await self.submit_next()
            if not submitted:
                await asyncio.sleep(self._tick)

    # -- submitting ----------------------------------------------------------

    async def submit_next(self) -> bool:
        """Hand ComfyUI the oldest queued job, if it holds none of ours."""
        async with self._service() as service:
            if await service.repository.count_in_engine() > 0:
                return False
            job: Job | None = await service.repository.next_queued()
            if job is None or not await service.claim(job):
                return False
            job_id, graph, inputs = job.id, copy.deepcopy(job.graph), list(job.inputs or [])
        await self._publish(job_id)

        try:
            for hook in self._before_submit:
                await hook()
            await self._upload_inputs(job_id, graph, inputs)
            prompt_id = await self._comfy.queue_prompt(graph)
        except ComfyRejected as exc:
            await self._fail(job_id, describe_rejection(exc))
            return True
        except ComfyUnavailable:
            async with self._service() as service:
                await service.release(job_id)
            await self._publish(job_id)
            raise
        except (WorkflowError, KeyError, OSError) as exc:
            await self._fail(job_id, f"No se pudo preparar el trabajo: {exc}")
            return True

        self._inflight[prompt_id] = job_id
        async with self._service() as service:
            await service.submitted(job_id, prompt_id)
        return True

    async def _upload_inputs(
        self, job_id: str, graph: dict[str, Any], inputs: list[dict[str, Any]]
    ) -> None:
        for index, spec in enumerate(inputs):
            if self._disk is None:
                raise OSError("no storage disk to read job inputs from")
            data = await self._disk.get(spec["storage_key"])
            filename = spec.get("filename") or f"animesito_{job_id}_{index}.png"
            name = await self._comfy.upload_image(data, filename)
            set_inputs(graph, spec["anchor"], **{spec["field"]: name})

    async def _fail(self, job_id: str, message: str) -> None:
        async with self._service() as service:
            await service.failed(job_id, message)
        await self._publish(job_id)

    # -- following -----------------------------------------------------------

    async def handle(self, event: ComfyEvent) -> None:
        prompt_id = event.prompt_id
        if prompt_id is None:
            return
        job_id = await self._job_for(prompt_id)
        if job_id is None:
            return  # a prompt someone queued in ComfyUI's own UI
        kind = event.type
        if kind == "execution_start":
            async with self._service() as service:
                await service.started(job_id)
        elif kind == "progress":
            async with self._service() as service:
                job = await service.repository.get(job_id)
                if job is not None:
                    await service.progressed(
                        job, int(event.data.get("value", 0)), int(event.data.get("max", 0))
                    )
        elif kind == "execution_success":
            # Sent before ComfyUI writes the prompt's history, so the outputs
            # may not be readable yet: try, and leave the verdict to the
            # final `executing {node: null}`, which comes after the write.
            await self._finish(job_id, prompt_id, final=False)
            return
        elif kind == "executing" and event.data.get("node") is None:
            await self._finish(job_id, prompt_id, final=True)
            return
        elif kind == "execution_error":
            message = str(event.data.get("exception_message") or "ComfyUI reported an error")
            node_type = event.data.get("node_type")
            self._inflight.pop(prompt_id, None)
            await self._fail(job_id, f"{node_type}: {message}" if node_type else message)
            return
        elif kind == "execution_interrupted":
            self._inflight.pop(prompt_id, None)
            async with self._service() as service:
                job = await service.repository.get(job_id)
                if job is not None and not JobStatus(job.status).finished:
                    await service.failed(job_id, "Interrumpido en ComfyUI")
        else:
            return
        await self._publish(job_id)

    async def _in_engine(self, job_id: str) -> bool:
        async with self._sessionmaker() as session:
            job = await JobRepository(session).get(job_id)
            return job is not None and JobStatus(job.status) in (
                JobStatus.SUBMITTED,
                JobStatus.RUNNING,
            )

    async def _finish(self, job_id: str, prompt_id: str, *, final: bool = True) -> None:
        if not await self._in_engine(job_id):
            # Already settled: an error event, a cancel, or the earlier signal.
            if final:
                self._inflight.pop(prompt_id, None)
            return
        outputs = await self._comfy.outputs(prompt_id)
        for _ in range(HISTORY_RETRIES if final else 0):
            if outputs:
                break
            await asyncio.sleep(HISTORY_RETRY_SECONDS)
            outputs = await self._comfy.outputs(prompt_id)
        if not outputs:
            if final:
                self._inflight.pop(prompt_id, None)
                await self._fail(job_id, "ComfyUI terminó sin guardar ningún archivo")
            return
        self._inflight.pop(prompt_id, None)
        async with self._service() as service:
            moved = await service.executed(job_id, [output_to_dict(item) for item in outputs])
        if moved:
            await self._enqueue_ingest(job_id)
            await self._publish(job_id)

    async def reconcile(self) -> None:
        """After a (re)connect: settle jobs whose events we may have missed."""
        async with self._sessionmaker() as session:
            repository = JobRepository(session)
            active = [(job.id, job.comfy_prompt_id) for job in await repository.in_engine()]
            stale_ingest = await repository.stale(
                JobStatus.INGESTING, before=datetime.now(UTC) - STALE_INGEST
            )
            stale_ids = [job.id for job in stale_ingest]
        for job_id in stale_ids:
            await self._fail(job_id, "La ingesta a la galería no terminó")
        if not active:
            return
        queued = await self._comfy.queued_prompt_ids()
        for job_id, prompt_id in active:
            if prompt_id is None:
                async with self._service() as service:
                    await service.release(job_id)
                await self._publish(job_id)
                continue
            if prompt_id in queued:
                self._inflight[prompt_id] = job_id
                continue
            entry = await self._comfy.history(prompt_id)
            status = (entry or {}).get("status") or {}
            if entry and status.get("status_str") == "error":
                await self._fail(
                    job_id, "ComfyUI reportó un error mientras estábamos desconectados"
                )
            elif entry:
                await self._finish(job_id, prompt_id)
            else:
                await self._fail(job_id, "ComfyUI se reinició y perdió el trabajo")
