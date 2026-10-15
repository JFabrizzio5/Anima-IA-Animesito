"""Data access for the Gallery module."""

from __future__ import annotations

from sqlalchemy import func, or_, select

from jfastframework.db import BaseRepository

from shared.enums import MediaKind, MediaSource

from ..models import Generation


class GalleryRepository(BaseRepository[Generation]):
    model = Generation

    async def search(
        self,
        *,
        query: str | None,
        favorite: bool | None,
        kind: MediaKind | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Generation], int]:
        statement = self._base_query()
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(Generation.prompt.ilike(pattern), Generation.model.ilike(pattern))
            )
        if favorite is not None:
            statement = statement.where(Generation.favorite.is_(favorite))
        if kind is not None:
            statement = statement.where(Generation.kind == kind.value)
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = await self.session.scalars(
            statement.order_by(Generation.created_at.desc(), Generation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)

    async def generated_with_hash(self, sha256: str) -> bool:
        found = await self.find_one(sha256=sha256, source=MediaSource.GENERATED.value)
        return found is not None
