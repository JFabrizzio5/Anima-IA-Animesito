"""SQLAlchemy entity for the Settings module."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jfastframework.db import Base, TimestampMixin

JsonType = JSON().with_variant(JSONB(), "postgresql")


class AppSetting(Base, TimestampMixin):
    """One editable setting. Single local user: not tenant-scoped."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JsonType)
