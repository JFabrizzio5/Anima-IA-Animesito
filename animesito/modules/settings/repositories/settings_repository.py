"""Data access for the Settings module."""

from __future__ import annotations

from typing import Any

from jfastframework.db import BaseRepository

from ..models import AppSetting


class SettingsRepository(BaseRepository[AppSetting]):
    model = AppSetting
    tenant_scoped = False

    # The primary key is `key`, not the `id` BaseRepository.get assumes.
    async def by_key(self, key: str) -> AppSetting | None:
        return await self.session.get(AppSetting, key)

    async def value(self, key: str, default: Any = None) -> Any:
        found = await self.by_key(key)
        return default if found is None else found.value

    async def put(self, key: str, value: Any) -> None:
        found = await self.by_key(key)
        if found is None:
            await self.create(key=key, value=value)
        else:
            await self.update(found, value=value)
