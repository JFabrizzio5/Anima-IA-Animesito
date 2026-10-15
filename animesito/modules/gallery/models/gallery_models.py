"""Pydantic models for the Gallery module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from shared.enums import MediaKind, MediaSource


@dataclass(frozen=True, slots=True)
class NewMedia:
    """A file about to enter the gallery, with what produced it."""

    data: bytes
    filename: str
    kind: MediaKind
    source: MediaSource
    job_id: str | None = None
    prompt: str = ""
    negative: str = ""
    model: str | None = None
    seed: int | None = None
    adult: bool = False
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GenerationSummary:
    """What other modules may know about a gallery item."""

    id: int
    sha256: str
    kind: str
    source: str
    file_key: str
    prompt: str
    seed: int | None
    model: str | None


class GenerationRead(BaseModel):
    id: int
    job_id: str | None
    kind: MediaKind
    source: MediaSource
    url: str
    thumb_url: str | None
    mime: str
    width: int | None
    height: int | None
    size_bytes: int
    sha256: str
    prompt: str
    negative: str
    model: str | None
    seed: int | None
    params: dict[str, Any]
    adult: bool
    favorite: bool
    created_at: datetime


class GalleryPage(BaseModel):
    items: list[GenerationRead]
    total: int
    limit: int
    offset: int


class GenerationUpdate(BaseModel):
    favorite: bool | None = None
