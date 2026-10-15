"""The Settings module's public facade: a small key/value store of JSON values.

It knows nothing about what the values mean; the module that owns a setting
validates it before writing. Single local user, so no tenant argument.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .repositories import SettingsRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def read_settings(session: AsyncSession, keys: list[str]) -> dict[str, Any]:
    repository = SettingsRepository(session)
    return {key: await repository.value(key) for key in keys}


async def write_settings(session: AsyncSession, values: dict[str, Any]) -> None:
    repository = SettingsRepository(session)
    for key, value in values.items():
        await repository.put(key, value)


__all__ = ["read_settings", "write_settings"]
