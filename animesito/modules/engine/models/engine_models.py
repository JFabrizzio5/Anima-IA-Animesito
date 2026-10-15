"""Wire contracts for the Engine module."""

from __future__ import annotations

from pydantic import BaseModel


class EngineStatus(BaseModel):
    reachable: bool
    url: str
    version: str | None = None
    device: str | None = None
    vram_total_mb: int | None = None
    vram_free_mb: int | None = None
    running: int = 0
    pending: int = 0
    detail: str | None = None
