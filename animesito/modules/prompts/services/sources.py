"""Danbooru and AniList, as this app needs them.

Danbooru is the vocabulary: Illustrious, NoobAI and Pony were trained on its
tags, so a character "exists" for the model when Danbooru has a tag with many
posts. AniList adds what Danbooru lacks: a picture, the series title, and the
character's canonical age, which feeds the minor-character policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

DANBOORU_CATEGORIES = {0: "general", 1: "artist", 3: "copyright", 4: "character", 5: "meta"}
CATEGORY_IDS = {name: number for number, name in DANBOORU_CATEGORIES.items()}

_ANILIST_QUERY = """
query ($search: String, $perPage: Int) {
  Page(perPage: $perPage) {
    characters(search: $search, sort: FAVOURITES_DESC) {
      name { full first last native }
      gender
      age
      image { medium }
      media(perPage: 1, sort: POPULARITY_DESC) { nodes { title { romaji english } } }
    }
  }
}
"""

_FIRST_NUMBER = re.compile(r"\d+")


class SourceUnavailable(RuntimeError):
    """Danbooru or AniList did not answer usefully."""


@dataclass(frozen=True, slots=True)
class Tag:
    name: str
    category: str
    count: int
    # The alias the query matched, when it was one: "yor_forger" -> yor_briar.
    alias: str | None = None

    @property
    def label(self) -> str:
        return self.name.replace("_", " ")


@dataclass(frozen=True, slots=True)
class RelatedTag:
    name: str
    category: str
    count: int
    frequency: float


@dataclass(frozen=True, slots=True)
class AniCharacter:
    full: str
    first: str | None
    last: str | None
    native: str | None
    gender: str | None
    age: int | None
    image: str | None
    series: str | None
    series_english: str | None

    @property
    def is_minor(self) -> bool:
        return self.age is not None and self.age < 18


def parse_age(raw: Any) -> int | None:
    """AniList ages are free text: "15", "16-", "17-18", "~20", "Unknown"."""
    if raw is None:
        return None
    match = _FIRST_NUMBER.search(str(raw))
    return int(match.group()) if match else None


def to_tag(text: str) -> str:
    return re.sub(r"\s+", "_", text.strip().lower())


class Sources:
    def __init__(
        self,
        *,
        danbooru_url: str = "https://danbooru.donmai.us",
        anilist_url: str = "https://graphql.anilist.co",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.danbooru_url = danbooru_url.rstrip("/")
        self.anilist_url = anilist_url
        self._timeout = timeout
        self._transport = transport
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                headers={"User-Agent": "Animesito/0.2 (local prompt builder)"},
                follow_redirects=True,
            )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("Sources used before start()")
        return self._http

    async def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        try:
            response = await self.http.get(url, params=params)
        except httpx.TransportError as exc:
            raise SourceUnavailable(f"{url} not reachable: {exc}") from exc
        if response.status_code != 200:
            raise SourceUnavailable(f"{url} answered HTTP {response.status_code}")
        return response.json()

    async def autocomplete(self, query: str, *, limit: int = 10) -> list[Tag]:
        """Tags whose words start like ``query`` -- word order does not matter."""
        data = await self._get_json(
            f"{self.danbooru_url}/autocomplete.json",
            {"search[query]": to_tag(query), "search[type]": "tag_query", "limit": limit},
        )
        tags: list[Tag] = []
        for item in data if isinstance(data, list) else []:
            name = item.get("value") or (item.get("tag") or {}).get("name")
            category = DANBOORU_CATEGORIES.get(int(item.get("category", 0)), "general")
            if isinstance(name, str) and name:
                tags.append(
                    Tag(
                        name=name,
                        category=category,
                        count=int(item.get("post_count") or 0),
                        alias=item.get("antecedent") or None,
                    )
                )
        return tags

    async def related(self, tag: str, *, category: str, limit: int = 30) -> list[RelatedTag]:
        data = await self._get_json(
            f"{self.danbooru_url}/related_tag.json",
            {"query": to_tag(tag), "category": category, "limit": limit},
        )
        related: list[RelatedTag] = []
        for item in (data or {}).get("related_tags") or []:
            info = item.get("tag") or {}
            name = info.get("name")
            if not isinstance(name, str):
                continue
            related.append(
                RelatedTag(
                    name=name,
                    category=DANBOORU_CATEGORIES.get(int(info.get("category", 0)), "general"),
                    count=int(info.get("post_count") or 0),
                    frequency=float(item.get("frequency") or 0.0),
                )
            )
        return related

    async def anilist_characters(self, query: str, *, limit: int = 6) -> list[AniCharacter]:
        try:
            response = await self.http.post(
                self.anilist_url,
                json={"query": _ANILIST_QUERY, "variables": {"search": query, "perPage": limit}},
            )
        except httpx.TransportError as exc:
            raise SourceUnavailable(f"AniList not reachable: {exc}") from exc
        if response.status_code != 200:
            raise SourceUnavailable(f"AniList answered HTTP {response.status_code}")
        characters = (((response.json() or {}).get("data") or {}).get("Page") or {}).get(
            "characters"
        ) or []
        found: list[AniCharacter] = []
        for item in characters:
            name = item.get("name") or {}
            media = ((item.get("media") or {}).get("nodes") or [{}])[0] or {}
            title = media.get("title") or {}
            found.append(
                AniCharacter(
                    full=str(name.get("full") or ""),
                    first=name.get("first"),
                    last=name.get("last"),
                    native=name.get("native"),
                    gender=item.get("gender"),
                    age=parse_age(item.get("age")),
                    image=(item.get("image") or {}).get("medium"),
                    series=title.get("romaji"),
                    series_english=title.get("english"),
                )
            )
        return found
