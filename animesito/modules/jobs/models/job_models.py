"""Pydantic models for the Jobs module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from shared.enums import JobKind, JobStatus


@dataclass(frozen=True, slots=True)
class NewJob:
    kind: JobKind
    title: str
    workflow: str
    graph: dict[str, Any]
    params: dict[str, Any] = field(default_factory=dict)
    inputs: list[dict[str, Any]] = field(default_factory=list)


class JobRead(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus
    title: str
    workflow: str
    progress: float
    progress_text: str
    params: dict[str, Any]
    result_ids: list[int]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobEvent(BaseModel):
    """What the SSE stream sends on every change of a job."""

    id: str
    kind: JobKind
    status: JobStatus
    title: str
    progress: float
    progress_text: str
    result_ids: list[int]
    error: str | None
