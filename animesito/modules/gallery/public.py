"""The Gallery module's public facade.

Takes the caller's session and an explicit tenant_id; returns DTOs. The one
write here goes through the service so the files and the row stay together.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import GenerationSummary, NewMedia
from .repositories import GalleryRepository
from .services import GalleryService, summarize

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_summary(
    session: AsyncSession, *, tenant_id: str | None, generation_id: int
) -> GenerationSummary | None:
    generation = await GalleryRepository(session, tenant_id=tenant_id).get(generation_id)
    return None if generation is None else summarize(generation)


async def save_media(
    session: AsyncSession, disk: Any, *, tenant_id: str | None, media: NewMedia
) -> GenerationSummary:
    service = GalleryService(GalleryRepository(session, tenant_id=tenant_id), disk)
    saved = await service.save(media)
    return summarize(saved)


async def generated_by_app(
    session: AsyncSession, disk: Any, *, tenant_id: str | None, data: bytes
) -> bool:
    """Whether ``data`` is byte-for-byte a file this app generated."""
    service = GalleryService(GalleryRepository(session, tenant_id=tenant_id), disk)
    return await service.generated_by_app(data)


async def read_file(
    session: AsyncSession, disk: Any, *, tenant_id: str | None, generation_id: int
) -> tuple[GenerationSummary, bytes] | None:
    generation = await GalleryRepository(session, tenant_id=tenant_id).get(generation_id)
    if generation is None:
        return None
    data: bytes = await disk.get(generation.file_key)
    return summarize(generation), data


__all__ = [
    "GenerationSummary",
    "NewMedia",
    "generated_by_app",
    "get_summary",
    "read_file",
    "save_media",
]
