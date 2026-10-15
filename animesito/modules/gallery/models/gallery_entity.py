"""SQLAlchemy entity for the Gallery module."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, BigInteger, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jfastframework.db import Base, TenantMixin, TimestampMixin

JsonType = JSON().with_variant(JSONB(), "postgresql")


class Generation(Base, TimestampMixin, TenantMixin):
    __tablename__ = "generations"
    __table_args__ = (Index("ix_generations_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(32), index=True, default=None)
    kind: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))
    file_key: Mapped[str] = mapped_column(String(512))
    thumb_key: Mapped[str | None] = mapped_column(String(512), default=None)
    mime: Mapped[str] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(default=None)
    height: Mapped[int | None] = mapped_column(default=None)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    # Provenance: adult edits are only allowed on files whose hash is here
    # with source = generated.
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    prompt: Mapped[str] = mapped_column(Text, default="")
    negative: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str | None] = mapped_column(String(255), default=None)
    seed: Mapped[int | None] = mapped_column(BigInteger, default=None)
    params: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    adult: Mapped[bool] = mapped_column(default=False)
    favorite: Mapped[bool] = mapped_column(default=False)
