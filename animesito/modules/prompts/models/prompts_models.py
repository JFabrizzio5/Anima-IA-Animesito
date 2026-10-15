"""Wire contracts for the Prompts module."""

from __future__ import annotations

from pydantic import BaseModel


class TagOut(BaseModel):
    tag: str
    label: str
    category: str
    count: int


class CharacterHit(BaseModel):
    tag: str
    label: str
    count: int | None = None
    series_tag: str | None = None
    series: str | None = None
    image: str | None = None
    gender: str | None = None
    age: int | None = None
    # Canonically under 18 per AniList: adult mode refuses this character.
    minor: bool = False
    # "danbooru" (the model knows the tag), "anilist" (unverified tag), "both".
    source: str = "danbooru"


class Trait(BaseModel):
    tag: str
    label: str
    frequency: float


class CharacterTraits(BaseModel):
    tag: str
    series: list[TagOut]
    traits: list[Trait]
    # Canon clothing and accessories, offered off by default.
    outfit: list[Trait] = []


class BuilderOption(BaseModel):
    label: str
    tags: str


class BuilderZone(BaseModel):
    id: str
    label: str
    options: list[BuilderOption]


class BuilderCatalog(BaseModel):
    zones: list[BuilderZone]
