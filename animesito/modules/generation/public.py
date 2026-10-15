"""The Generation module's public facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.policy.public import PolicyAdditions

from .services import load_config

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def policy_additions(session: AsyncSession) -> PolicyAdditions:
    """What the operator added to the content policy in Ajustes."""
    return (await load_config(session)).additions


__all__ = ["policy_additions"]
