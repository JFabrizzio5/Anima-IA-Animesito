"""The Prompts module's public facade."""

from __future__ import annotations

from typing import Any

from .services import MINOR_SET_KEY


async def known_minor_characters(redis: Any) -> frozenset[str]:
    """Characters AniList reported as under 18, learned from builder searches.

    Normalised names ("kitagawa marin"). Empty when Redis is not available:
    the policy's static list still applies.
    """
    if redis is None:
        return frozenset()
    try:
        members = await redis.smembers(MINOR_SET_KEY)
    except Exception:  # a missing Redis must not block generation; the static list holds
        return frozenset()
    return frozenset(str(member) for member in members)


__all__ = ["known_minor_characters"]
