from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from modules.prompts.public import known_minor_characters
from modules.prompts.services import (
    MINOR_SET_KEY,
    PromptService,
    Sources,
    SourceUnavailable,
    base_tag,
    load_builder,
    parse_age,
)

AUTOCOMPLETE = [
    {"label": "kitagawa marin", "value": "kitagawa_marin", "category": 4, "post_count": 6546},
    {"label": "tifa lockhart", "value": "tifa_lockhart", "category": 4, "post_count": 17225},
    {"label": "tsunade (naruto)", "value": "tsunade_(naruto)", "category": 4, "post_count": 9000},
    {"label": "blonde hair", "value": "blonde_hair", "category": 0, "post_count": 2202037},
    {
        "label": "yor briar",
        "value": "yor_briar",
        "category": 4,
        "post_count": 11562,
        "antecedent": "yor_forger",
    },
]
ANILIST = {
    "data": {
        "Page": {
            "characters": [
                {
                    "name": {
                        "full": "Marin Kitagawa",
                        "first": "Marin",
                        "last": "Kitagawa",
                        "native": "x",
                    },
                    "gender": "Female",
                    "age": "15",
                    "image": {"medium": "https://img/marin.png"},
                    "media": {
                        "nodes": [
                            {
                                "title": {
                                    "romaji": "Sono Bisque Doll",
                                    "english": "My Dress-Up Darling",
                                }
                            }
                        ]
                    },
                },
                {
                    "name": {"full": "Tsunade", "first": "Tsunade", "last": None, "native": None},
                    "gender": "Female",
                    "age": "50s",
                    "image": {"medium": "https://img/tsunade.png"},
                    "media": {"nodes": [{"title": {"romaji": "Naruto", "english": "Naruto"}}]},
                },
                {
                    "name": {
                        "full": "Yor Forger",
                        "first": "Yor",
                        "last": "Forger",
                        "native": None,
                    },
                    "gender": "Female",
                    "age": "27",
                    "image": {"medium": "https://img/yor.png"},
                    "media": {"nodes": [{"title": {"romaji": "SPY x FAMILY", "english": None}}]},
                },
                {
                    "name": {
                        "full": "Obscure Hero",
                        "first": "Hero",
                        "last": "Obscure",
                        "native": None,
                    },
                    "gender": "Male",
                    "age": "12",
                    "image": None,
                    "media": {"nodes": []},
                },
            ]
        }
    }
}
RELATED_GENERAL = {
    "related_tags": [
        {"tag": {"name": "1girl", "category": 0, "post_count": 1}, "frequency": 0.93},
        {"tag": {"name": "blonde_hair", "category": 0, "post_count": 1}, "frequency": 0.88},
        {"tag": {"name": "pink_eyes", "category": 0, "post_count": 1}, "frequency": 0.7},
        {"tag": {"name": "smile", "category": 0, "post_count": 1}, "frequency": 0.6},
        {"tag": {"name": "gyaru", "category": 0, "post_count": 1}, "frequency": 0.5},
        {"tag": {"name": "earrings", "category": 0, "post_count": 1}, "frequency": 0.2},
        {"tag": {"name": "black_dress", "category": 0, "post_count": 1}, "frequency": 0.45},
        {"tag": {"name": "hair_ornament", "category": 0, "post_count": 1}, "frequency": 0.4},
    ]
}
RELATED_COPYRIGHT = {
    "related_tags": [
        {
            "tag": {"name": "sono_bisque_doll_wa_koi_wo_suru", "category": 3, "post_count": 8145},
            "frequency": 0.99,
        }
    ]
}


class FakeRedis:
    def __init__(self) -> None:
        self.sets: dict[str, set[str]] = {}

    async def sadd(self, key: str, *values: str) -> int:
        self.sets.setdefault(key, set()).update(values)
        return len(values)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))


def transport(*, anilist_up: bool = True, danbooru_up: bool = True) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "graphql.anilist.co":
            return httpx.Response(200, json=ANILIST) if anilist_up else httpx.Response(503)
        if not danbooru_up:
            return httpx.Response(503)
        if request.url.path == "/autocomplete.json":
            return httpx.Response(200, json=AUTOCOMPLETE)
        if request.url.path == "/related_tag.json":
            body = (
                RELATED_COPYRIGHT
                if request.url.params["category"] == "copyright"
                else RELATED_GENERAL
            )
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
async def make_service() -> Any:
    opened: list[Sources] = []

    async def build(**flags: bool) -> tuple[PromptService, FakeRedis]:
        sources = Sources(transport=transport(**flags))
        await sources.start()
        opened.append(sources)
        redis = FakeRedis()
        return PromptService(sources, None, redis), redis

    yield build
    for sources in opened:
        await sources.close()


@pytest.mark.parametrize(
    ("raw", "age"),
    [("15", 15), ("16-", 16), ("17-18", 17), ("~20", 20), ("Unknown", None), (None, None)],
)
def test_parse_age(raw: Any, age: int | None) -> None:
    assert parse_age(raw) == age


def test_base_tag_drops_the_series_qualifier() -> None:
    assert base_tag("tsunade_(naruto)") == "tsunade"
    assert base_tag("kitagawa_marin") == "kitagawa_marin"


def test_builder_catalog_loads() -> None:
    zones = {zone.id: zone for zone in load_builder().zones}
    assert {"outfit", "pose", "expression", "environment", "extra"} <= set(zones)
    assert all(option.tags for zone in zones.values() for option in zone.options)


async def test_characters_merge_danbooru_and_anilist(make_service: Any) -> None:
    service, redis = await make_service()
    hits = {hit.tag: hit for hit in await service.characters("marin")}
    marin = hits["kitagawa_marin"]
    assert marin.source == "both" and marin.count == 6546
    assert marin.series == "My Dress-Up Darling" and marin.image == "https://img/marin.png"
    assert marin.age == 15 and marin.minor is True
    tsunade = hits["tsunade_(naruto)"]
    assert tsunade.source == "both" and tsunade.minor is False
    assert hits["tifa_lockhart"].source == "danbooru"
    # Matched through Danbooru's alias, not left as two separate entries.
    assert hits["yor_briar"].source == "both" and hits["yor_briar"].series == "SPY x FAMILY"
    assert "forger_yor" not in hits
    hero = hits["obscure_hero"]
    assert hero.source == "anilist" and hero.count is None and hero.minor is True
    assert "blonde_hair" not in hits
    # Ranking: verified by both sources first.
    assert hits[next(iter(hits))].source == "both"
    assert redis.sets[MINOR_SET_KEY] == {"kitagawa marin", "obscure hero"}
    assert await known_minor_characters(redis) == frozenset({"kitagawa marin", "obscure hero"})


async def test_characters_survive_one_source_down(make_service: Any) -> None:
    service, _ = await make_service(anilist_up=False)
    hits = await service.characters("marin")
    assert {hit.source for hit in hits} == {"danbooru"}
    service, _ = await make_service(danbooru_up=False)
    hits = await service.characters("marin")
    assert {hit.source for hit in hits} == {"anilist"}
    service, _ = await make_service(danbooru_up=False, anilist_up=False)
    with pytest.raises(SourceUnavailable):
        await service.characters("marin")


async def test_traits_keep_appearance_only(make_service: Any) -> None:
    service, _ = await make_service()
    traits = await service.traits("kitagawa_marin")
    assert [trait.tag for trait in traits.traits] == ["blonde_hair", "pink_eyes", "hair_ornament"]
    # Clothing is offered apart; hair accessories stay with the traits.
    assert [item.tag for item in traits.outfit] == ["black_dress", "earrings"]
    assert [series.tag for series in traits.series] == ["sono_bisque_doll_wa_koi_wo_suru"]


async def test_tags_filter_by_category(make_service: Any) -> None:
    service, _ = await make_service()
    general = await service.tags("blonde", category="general")
    assert [tag.tag for tag in general] == ["blonde_hair"]
    assert await service.tags("x") == []
    with pytest.raises(ValueError):
        await service.tags("blonde", category="nope")


async def test_cache_is_used_when_present() -> None:
    calls: list[str] = []

    class FakeCache:
        def __init__(self) -> None:
            self.store: dict[str, Any] = {}

        async def get_or_set(self, key: str, loader: Any, *, ttl: int | None = None) -> Any:
            if key not in self.store:
                calls.append(key)
                self.store[key] = json.loads(json.dumps(await loader()))
            return self.store[key]

    sources = Sources(transport=transport())
    await sources.start()
    service = PromptService(sources, FakeCache(), FakeRedis())
    await service.tags("blonde")
    await service.tags("blonde")
    await sources.close()
    assert len(calls) == 1
