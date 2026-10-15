"""HTTP layer for the Prompts module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Request

from jfastframework.app import get_context
from jfastframework.errors import ServiceUnavailableError, ValidationError

from ..models import BuilderCatalog, CharacterHit, CharacterTraits, TagOut
from ..services import PromptService, Sources, SourceUnavailable, load_builder

router = APIRouter(prefix="/prompts", tags=["prompts"])

_BUILDER = load_builder()


async def get_service(request: Request) -> PromptService:
    ctx = get_context(request.app)
    return PromptService(
        ctx.require("prompts.sources", Sources), ctx.get("cache"), ctx.get("cache.client")
    )


@router.get("/builder", response_model=BuilderCatalog, summary="Builder zones and presets")
async def builder() -> BuilderCatalog:
    return _BUILDER


@router.get("/tags", response_model=list[TagOut], summary="Danbooru tag autocomplete")
async def tags(
    q: str = Query(..., min_length=2, max_length=80),
    category: str | None = Query(None, pattern="^(general|artist|copyright|character|meta)$"),
    limit: int = Query(12, ge=1, le=25),
    service: PromptService = Depends(get_service),
) -> list[TagOut]:
    try:
        return await service.tags(q, category=category, limit=limit)
    except SourceUnavailable as exc:
        raise ServiceUnavailableError(f"Danbooru no responde: {exc}") from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


@router.get(
    "/characters", response_model=list[CharacterHit], summary="Characters (Danbooru + AniList)"
)
async def characters(
    q: str = Query(..., min_length=2, max_length=80),
    service: PromptService = Depends(get_service),
) -> list[CharacterHit]:
    try:
        return await service.characters(q)
    except SourceUnavailable as exc:
        raise ServiceUnavailableError(f"Danbooru y AniList no responden: {exc}") from exc


@router.get(
    "/characters/{tag}/traits",
    response_model=CharacterTraits,
    summary="Appearance tags and series of a character",
)
async def traits(
    tag: str = Path(..., min_length=2, max_length=120),
    service: PromptService = Depends(get_service),
) -> CharacterTraits:
    try:
        return await service.traits(tag)
    except SourceUnavailable as exc:
        raise ServiceUnavailableError(f"Danbooru no responde: {exc}") from exc
