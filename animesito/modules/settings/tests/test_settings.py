from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from modules.settings.public import read_settings, write_settings


async def test_round_trip_and_defaults(db_session: AsyncSession) -> None:
    assert await read_settings(db_session, ["a"]) == {"a": None}
    await write_settings(db_session, {"a": ["x", "y"], "b": {"k": "v"}})
    await write_settings(db_session, {"a": ["z"]})
    assert await read_settings(db_session, ["a", "b"]) == {"a": ["z"], "b": {"k": "v"}}
