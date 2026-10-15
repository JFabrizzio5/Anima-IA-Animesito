"""Business logic for the Gallery module."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from jfastframework.errors import NotFoundError

from shared.enums import MediaKind

from ..models import Generation, GenerationSummary, NewMedia
from ..repositories import GalleryRepository
from .media import probe, sha256_of


def summarize(generation: Generation) -> GenerationSummary:
    return GenerationSummary(
        id=generation.id,
        sha256=generation.sha256,
        kind=generation.kind,
        source=generation.source,
        file_key=generation.file_key,
        prompt=generation.prompt,
        seed=generation.seed,
        model=generation.model,
    )


class GalleryService:
    def __init__(self, repository: GalleryRepository, disk: Any) -> None:
        self.repository = repository
        # A jfastframework StorageBackend; typed loosely so tests pass a fake.
        self.disk = disk

    async def save(self, media: NewMedia) -> Generation:
        info = await asyncio.to_thread(probe, media.data, media.filename, media.kind)
        now = datetime.now(UTC)
        stem = f"{now:%Y/%m}/{uuid.uuid4().hex}"
        file_key = f"gallery/{stem}{info.suffix}"
        await self.disk.put(file_key, media.data, content_type=info.mime)
        thumb_key: str | None = None
        if info.thumbnail is not None:
            thumb_key = f"thumbs/{stem}.webp"
            await self.disk.put(thumb_key, info.thumbnail, content_type="image/webp")
        return await self.repository.create(
            job_id=media.job_id,
            kind=media.kind.value,
            source=media.source.value,
            file_key=file_key,
            thumb_key=thumb_key,
            mime=info.mime,
            width=info.width,
            height=info.height,
            size_bytes=len(media.data),
            sha256=info.sha256,
            prompt=media.prompt,
            negative=media.negative,
            model=media.model,
            seed=media.seed,
            params=media.params,
            adult=media.adult,
            favorite=False,
        )

    async def search(
        self,
        *,
        query: str | None = None,
        favorite: bool | None = None,
        kind: MediaKind | None = None,
        limit: int = 60,
        offset: int = 0,
    ) -> tuple[list[Generation], int]:
        return await self.repository.search(
            query=query, favorite=favorite, kind=kind, limit=limit, offset=offset
        )

    async def get(self, generation_id: int) -> Generation:
        return await self.repository.get_or_raise(generation_id)

    async def set_favorite(self, generation_id: int, favorite: bool) -> Generation:
        generation = await self.repository.get_or_raise(generation_id)
        return await self.repository.update(generation, favorite=favorite)

    async def delete(self, generation_id: int) -> None:
        generation = await self.repository.get(generation_id)
        if generation is None:
            raise NotFoundError(f"Generation {generation_id} not found")
        for key in (generation.file_key, generation.thumb_key):
            if key:
                await self.disk.delete(key)
        await self.repository.delete(generation)

    async def generated_by_app(self, data: bytes) -> bool:
        digest = await asyncio.to_thread(sha256_of, data)
        return await self.repository.generated_with_hash(digest)

    def url(self, key: str | None) -> str | None:
        return self.disk.url(key) if key else None
