"""The Jobs module's public facade: how other modules queue GPU work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .models import NewJob
from .repositories import JobRepository
from .services import JobService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class JobSummary:
    id: str
    kind: str
    status: str
    title: str


@dataclass(frozen=True, slots=True)
class JobDetail:
    id: str
    kind: str
    status: str
    title: str
    workflow: str
    graph: dict[str, Any]
    params: dict[str, Any]
    result_ids: list[int]


async def enqueue(session: AsyncSession, *, tenant_id: str | None, new: NewJob) -> JobSummary:
    """Queue a job in the caller's transaction; the dispatcher picks it up after commit."""
    job = await JobService(JobRepository(session, tenant_id=tenant_id)).enqueue(new)
    return JobSummary(id=job.id, kind=job.kind, status=job.status, title=job.title)


async def recent(
    session: AsyncSession, *, tenant_id: str | None, limit: int = 50
) -> list[JobDetail]:
    """Newest first, with the graph and parameters: what "reuse" needs."""
    jobs = await JobRepository(session, tenant_id=tenant_id).recent(limit=limit)
    return [
        JobDetail(
            id=job.id,
            kind=job.kind,
            status=job.status,
            title=job.title,
            workflow=job.workflow,
            graph=job.graph,
            params=job.params or {},
            result_ids=list(job.result_ids or []),
        )
        for job in jobs
    ]


__all__ = ["JobDetail", "JobSummary", "NewJob", "enqueue", "recent"]
