"""Business logic for the Jobs module: the job state machine.

    queued -> submitted -> running -> ingesting -> done
         \\          \\          \\-> error | cancelled
          \\-> cancelled

Every transition is a compare-and-set on the current status, so the API, the
dispatcher and the ingest task can race without a lock and exactly one wins.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from jfastframework.errors import ConflictError

from shared.enums import JobKind, JobStatus

from ..models import Job, JobEvent, JobRead, NewJob
from ..repositories import JobRepository

_TEXT_LIMIT = 200


def to_event(job: Job) -> JobEvent:
    return JobEvent(
        id=job.id,
        kind=JobKind(job.kind),
        status=JobStatus(job.status),
        title=job.title,
        progress=job.progress,
        progress_text=job.progress_text,
        result_ids=list(job.result_ids or []),
        error=job.error,
    )


def to_read(job: Job) -> JobRead:
    return JobRead(
        id=job.id,
        kind=JobKind(job.kind),
        status=JobStatus(job.status),
        title=job.title,
        workflow=job.workflow,
        progress=job.progress,
        progress_text=job.progress_text,
        params=job.params or {},
        result_ids=list(job.result_ids or []),
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


class JobService:
    def __init__(self, repository: JobRepository) -> None:
        self.repository = repository

    async def enqueue(self, new: NewJob) -> Job:
        return await self.repository.create(
            id=uuid.uuid4().hex,
            queued_at=datetime.now(UTC),
            kind=new.kind.value,
            status=JobStatus.QUEUED.value,
            title=new.title[:_TEXT_LIMIT],
            workflow=new.workflow,
            graph=new.graph,
            params=new.params,
            inputs=new.inputs,
            progress=0.0,
            progress_text="En cola",
            outputs=[],
            result_ids=[],
        )

    async def get(self, job_id: str) -> Job:
        return await self.repository.get_or_raise(job_id)

    async def recent(self, *, limit: int = 50) -> list[Job]:
        return await self.repository.recent(limit=limit)

    async def reload(self, job_id: str) -> Job:
        job = await self.repository.get_or_raise(job_id)
        await self.repository.session.refresh(job)
        return job

    # -- transitions used by the dispatcher and the ingest task -------------

    async def claim(self, job: Job) -> bool:
        return await self.repository.transition(
            job.id,
            expected=JobStatus.QUEUED,
            status=JobStatus.SUBMITTED.value,
            progress_text="Enviando a ComfyUI",
        )

    async def submitted(self, job_id: str, prompt_id: str) -> None:
        await self.repository.set_prompt_id(job_id, prompt_id)

    async def release(self, job_id: str) -> bool:
        """Back to the queue: ComfyUI went away before it accepted the prompt."""
        return await self.repository.transition(
            job_id,
            expected=JobStatus.SUBMITTED,
            status=JobStatus.QUEUED.value,
            comfy_prompt_id=None,
            progress_text="En cola",
        )

    async def started(self, job_id: str) -> bool:
        return await self.repository.transition(
            job_id,
            expected=JobStatus.SUBMITTED,
            status=JobStatus.RUNNING.value,
            started_at=datetime.now(UTC),
            progress_text="Generando",
        )

    async def progressed(self, job: Job, value: int, maximum: int) -> None:
        if JobStatus(job.status) not in (JobStatus.SUBMITTED, JobStatus.RUNNING):
            return
        fraction = 0.0 if maximum <= 0 else min(value / maximum, 1.0)
        await self.repository.update(
            job,
            status=JobStatus.RUNNING.value,
            started_at=job.started_at or datetime.now(UTC),
            # 95% at most: the last stretch is saving into the gallery.
            progress=round(fraction * 0.95, 4),
            progress_text=f"Paso {value}/{maximum}",
        )

    async def executed(self, job_id: str, outputs: Sequence[dict[str, Any]]) -> bool:
        for expected in (JobStatus.RUNNING, JobStatus.SUBMITTED):
            moved = await self.repository.transition(
                job_id,
                expected=expected,
                status=JobStatus.INGESTING.value,
                outputs=list(outputs),
                progress=0.96,
                progress_text="Guardando en la galeria",
            )
            if moved:
                return True
        return False

    async def done(self, job_id: str, result_ids: Sequence[int]) -> bool:
        return await self.repository.transition(
            job_id,
            expected=JobStatus.INGESTING,
            status=JobStatus.DONE.value,
            result_ids=list(result_ids),
            progress=1.0,
            progress_text="Listo",
            finished_at=datetime.now(UTC),
        )

    async def failed(self, job_id: str, message: str) -> bool:
        for expected in (
            JobStatus.QUEUED,
            JobStatus.SUBMITTED,
            JobStatus.RUNNING,
            JobStatus.INGESTING,
        ):
            moved = await self.repository.transition(
                job_id,
                expected=expected,
                status=JobStatus.ERROR.value,
                error=message[:4000],
                progress_text="Error",
                finished_at=datetime.now(UTC),
            )
            if moved:
                return True
        return False

    async def cancel(self, job_id: str) -> Job:
        """Cancel a job; the caller interrupts ComfyUI if it had the prompt."""
        job = await self.repository.get_or_raise(job_id)
        status = JobStatus(job.status)
        if status.finished:
            raise ConflictError(f"Job {job_id} already finished ({status.value})")
        if status is JobStatus.INGESTING:
            raise ConflictError(f"Job {job_id} is already saving its results")
        moved = await self.repository.transition(
            job_id,
            expected=status,
            status=JobStatus.CANCELLED.value,
            progress_text="Cancelado",
            finished_at=datetime.now(UTC),
        )
        if not moved:
            raise ConflictError(f"Job {job_id} changed while cancelling; try again")
        await self.repository.session.refresh(job)
        return job
