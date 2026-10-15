"""Data access for the Jobs module."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update

from jfastframework.db import BaseRepository

from shared.enums import JobStatus

from ..models import Job

#: Statuses in which ComfyUI holds (or is about to hold) the job.
IN_ENGINE = (JobStatus.SUBMITTED.value, JobStatus.RUNNING.value)


class JobRepository(BaseRepository[Job]):
    model = Job

    async def recent(self, *, limit: int) -> list[Job]:
        rows = await self.session.scalars(
            self._base_query().order_by(Job.queued_at.desc(), Job.id.desc()).limit(limit)
        )
        return list(rows)

    async def next_queued(self) -> Job | None:
        rows = await self.session.scalars(
            self._base_query()
            .where(Job.status == JobStatus.QUEUED.value)
            .order_by(Job.queued_at, Job.id)
            .limit(1)
        )
        return rows.first()

    async def in_engine(self) -> list[Job]:
        rows = await self.session.scalars(self._base_query().where(Job.status.in_(IN_ENGINE)))
        return list(rows)

    async def count_in_engine(self) -> int:
        total = await self.session.scalar(
            select(func.count()).select_from(Job).where(Job.status.in_(IN_ENGINE))
        )
        return int(total or 0)

    async def by_prompt_id(self, prompt_id: str) -> Job | None:
        return await self.find_one(comfy_prompt_id=prompt_id)

    async def set_prompt_id(self, job_id: str, prompt_id: str) -> None:
        # Not a status transition: ComfyUI may already have reported the job
        # as started (or even finished) before this write lands.
        await self.session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(comfy_prompt_id=prompt_id)
            .execution_options(synchronize_session=False)
        )

    async def stale(self, status: JobStatus, *, before: datetime) -> list[Job]:
        rows = await self.session.scalars(
            self._base_query().where(Job.status == status.value, Job.updated_at < before)
        )
        return list(rows)

    async def transition(self, job_id: str, *, expected: JobStatus, **values: Any) -> bool:
        """Compare-and-set on status: True only for the caller that won the race."""
        result = await self.session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == expected.value)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return bool(getattr(result, "rowcount", 0) == 1)
