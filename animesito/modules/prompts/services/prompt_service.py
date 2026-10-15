"""Tag and character lookups, cached, and the canonical-minor list they feed."""

from __future__ import annotations

import asyncio
import re
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..models import (
    BuilderCatalog,
    CharacterHit,
    CharacterTraits,
    TagOut,
    Trait,
)
from .sources import CATEGORY_IDS, AniCharacter, Sources, SourceUnavailable, Tag, to_tag

BUILDER_FILE = Path(__file__).resolve().parent.parent / "builder.toml"

#: Redis set (raw key, no cache prefix) of characters AniList says are under
#: 18, as normalised names ("kitagawa marin"). Read by the generation policy.
MINOR_SET_KEY = "animesito:minor_characters"

TAGS_TTL = 24 * 3600
CHARACTERS_TTL = 24 * 3600
TRAITS_TTL = 7 * 24 * 3600

# What a character looks like, as opposed to what they happen to be doing in
# the posts that carry their tag.
_APPEARANCE = re.compile(
    r"(hair|eyes|bangs|ahoge|braid|ponytail|twintails|hair_bun|sidelocks|skin|ears|"
    r"tail|horns|wings|halo|freckles|mole|scar|glasses|fang|eyepatch|breasts|"
    r"pointy|heterochromia|eyelashes|tan$|dark-skinned)"
)
# What they usually wear: offered separately and off by default, because it is
# what makes a character recognisable in their canon outfit and exactly what a
# user changes first.
_OUTFIT = re.compile(
    r"(dress|skirt|shirt|blouse|sweater|jacket|coat|cape|cloak|uniform|gloves|thighhighs|"
    r"pantyhose|stockings|socks|boots|shoes|heels|earrings|necklace|choker|bracelet|ribbon|"
    r"bow|hat|scarf|kimono|armor|bodysuit|leotard|apron|shorts|pants|belt|sleeves|collar|"
    r"necktie|vest|hood|headband|tiara|crown|mask|jewelry|cleavage_cutout|bare_shoulders)"
)
_QUALIFIER = re.compile(r"_\([^)]*\)$")
OUTFIT_LIMIT = 8
OUTFIT_MIN_FREQUENCY = 0.2
TRAIT_LIMIT = 12
TRAIT_MIN_FREQUENCY = 0.25
SERIES_MIN_FREQUENCY = 0.3


def load_builder(path: Path = BUILDER_FILE) -> BuilderCatalog:
    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    return BuilderCatalog.model_validate({"zones": data.get("zones", [])})


def base_tag(tag: str) -> str:
    """``tsunade_(naruto)`` -> ``tsunade``: the name without its disambiguation."""
    return _QUALIFIER.sub("", tag)


def normalised_name(tag: str) -> str:
    return base_tag(tag).replace("_", " ").strip()


def candidate_tags(character: AniCharacter) -> list[str]:
    """Danbooru spellings an AniList name may have; surname first is the norm."""
    found: list[str] = []
    if character.last and character.first:
        found += [
            to_tag(f"{character.last} {character.first}"),
            to_tag(f"{character.first} {character.last}"),
        ]
    if character.full:
        found.append(to_tag(character.full))
    if character.first and not character.last:
        found.append(to_tag(character.first))
    return list(dict.fromkeys(found))


def _tag_out(tag: Tag) -> TagOut:
    return TagOut(tag=tag.name, label=tag.label, category=tag.category, count=tag.count)


class PromptService:
    def __init__(self, sources: Sources, cache: Any, redis: Any) -> None:
        self.sources = sources
        # The jfastframework Cache facade (JSON values, prefixed keys) and the
        # raw Redis client for the shared minor-character set.
        self.cache = cache
        self.redis = redis

    async def _cached(self, key: str, ttl: int, loader: Any) -> Any:
        if self.cache is None:
            return await loader()
        return await self.cache.get_or_set(key, loader, ttl=ttl)

    # -- tags --------------------------------------------------------------

    async def tags(
        self, query: str, *, category: str | None = None, limit: int = 12
    ) -> list[TagOut]:
        query = query.strip()
        if len(query) < 2:
            return []
        if category is not None and category not in CATEGORY_IDS:
            raise ValueError(f"unknown tag category {category!r}")

        async def load() -> list[dict[str, Any]]:
            found = await self.sources.autocomplete(query, limit=25)
            if category is not None:
                found = [tag for tag in found if tag.category == category]
            return [_tag_out(tag).model_dump() for tag in found[:limit]]

        rows = await self._cached(
            f"tags:{category or 'any'}:{to_tag(query)}:{limit}", TAGS_TTL, load
        )
        return [TagOut.model_validate(row) for row in rows]

    # -- characters --------------------------------------------------------

    async def characters(self, query: str) -> list[CharacterHit]:
        query = query.strip()
        if len(query) < 2:
            return []

        async def load() -> list[dict[str, Any]]:
            return [hit.model_dump() for hit in await self._search_characters(query)]

        rows = await self._cached(f"characters:{to_tag(query)}", CHARACTERS_TTL, load)
        hits = [CharacterHit.model_validate(row) for row in rows]
        # Recorded on every lookup, cached or not: the set is what the policy
        # reads, and it must survive a Redis flush of the cache keys.
        await self.remember_minors(hit.tag for hit in hits if hit.minor)
        return hits

    async def _search_characters(self, query: str) -> list[CharacterHit]:
        danbooru, anilist = await asyncio.gather(
            self.sources.autocomplete(query, limit=25),
            self.sources.anilist_characters(query, limit=6),
            return_exceptions=True,
        )
        if isinstance(danbooru, BaseException) and isinstance(anilist, BaseException):
            raise SourceUnavailable("Neither Danbooru nor AniList answered")
        tags = [] if isinstance(danbooru, BaseException) else danbooru
        anis = [] if isinstance(anilist, BaseException) else anilist

        hits: dict[str, CharacterHit] = {
            tag.name: CharacterHit(
                tag=tag.name, label=tag.label, count=tag.count, source="danbooru"
            )
            for tag in tags
            if tag.category == "character"
        }
        by_base: dict[str, str] = {}
        for tag in tags:
            if tag.name in hits:
                by_base.setdefault(base_tag(tag.name), tag.name)
                if tag.alias:
                    by_base.setdefault(base_tag(tag.alias), tag.name)

        for character in anis:
            candidates = candidate_tags(character)
            match = next((by_base[c] for c in candidates if c in by_base), None)
            enrichment: dict[str, Any] = {
                "image": character.image,
                "series": character.series_english or character.series,
                "gender": character.gender,
                "age": character.age,
                "minor": character.is_minor,
            }
            if match is not None:
                hits[match] = hits[match].model_copy(update={**enrichment, "source": "both"})
            elif candidates:
                guess = candidates[0]
                hits.setdefault(
                    guess,
                    CharacterHit(
                        tag=guess, label=character.full or guess, source="anilist", **enrichment
                    ),
                )

        def rank(hit: CharacterHit) -> tuple[int, int]:
            order = {"both": 0, "danbooru": 1, "anilist": 2}[hit.source]
            return order, -(hit.count or 0)

        return sorted(hits.values(), key=rank)[:12]

    async def traits(self, tag: str) -> CharacterTraits:
        tag = to_tag(tag)

        async def load() -> dict[str, Any]:
            general, series = await asyncio.gather(
                self.sources.related(tag, category="general", limit=60),
                self.sources.related(tag, category="copyright", limit=5),
            )
            general = sorted(general, key=lambda item: -item.frequency)
            traits = [
                Trait(
                    tag=item.name,
                    label=item.name.replace("_", " "),
                    frequency=round(item.frequency, 3),
                )
                for item in general
                if item.frequency >= TRAIT_MIN_FREQUENCY and _APPEARANCE.search(item.name)
            ][:TRAIT_LIMIT]
            outfit = [
                Trait(
                    tag=item.name,
                    label=item.name.replace("_", " "),
                    frequency=round(item.frequency, 3),
                )
                for item in general
                if item.frequency >= OUTFIT_MIN_FREQUENCY
                and _OUTFIT.search(item.name)
                and not _APPEARANCE.search(item.name)
            ][:OUTFIT_LIMIT]
            copyrights = [
                TagOut(
                    tag=item.name,
                    label=item.name.replace("_", " "),
                    category=item.category,
                    count=item.count,
                )
                for item in series
                if item.frequency >= SERIES_MIN_FREQUENCY and item.name != tag
            ][:2]
            return CharacterTraits(
                tag=tag, series=copyrights, traits=traits, outfit=outfit
            ).model_dump()

        return CharacterTraits.model_validate(
            await self._cached(f"traits:v2:{tag}", TRAITS_TTL, load)
        )

    # -- the canonical-minor list ------------------------------------------

    async def remember_minors(self, tags: Iterable[str]) -> None:
        names = {normalised_name(tag) for tag in tags if tag}
        if names and self.redis is not None:
            await self.redis.sadd(MINOR_SET_KEY, *names)

    async def known_minors(self) -> set[str]:
        if self.redis is None:
            return set()
        members = await self.redis.smembers(MINOR_SET_KEY)
        return {str(member) for member in members}
