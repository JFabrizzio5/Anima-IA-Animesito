"""SQLAlchemy entity for the Jobs module."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jfastframework.db import Base, TenantMixin, TimestampMixin, UTCDateTime

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Job(Base, TimestampMixin, TenantMixin):
    """One unit of GPU work: a ComfyUI prompt and what became of it."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_queued", "status", "queued_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Queue order. Not created_at: PostgreSQL's now() is the transaction start,
    # so every batch of one request would tie and run in arbitrary order.
    queued_at: Mapped[datetime] = mapped_column(UTCDateTime())
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    workflow: Mapped[str] = mapped_column(String(64))
    # The exact graph sent to ComfyUI, kept for "reuse" and for debugging a
    # rejected prompt.
    graph: Mapped[dict[str, Any]] = mapped_column(JsonType)
    # What the user asked for, resolved: prompt, negative, model, seed, size...
    params: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    # Files to upload to ComfyUI before submitting: [{"storage_key", "anchor", "field"}].
    inputs: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    comfy_prompt_id: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    progress: Mapped[float] = mapped_column(default=0.0)
    progress_text: Mapped[str] = mapped_column(String(200), default="")
    outputs: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    result_ids: Mapped[list[int]] = mapped_column(JsonType, default=list)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=None)
