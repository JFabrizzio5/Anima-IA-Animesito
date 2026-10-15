"""HTTP layer for the Generation module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from jfastframework.app import get_context
from jfastframework.plugins.builtin.database import DbSession

from modules.engine.public import comfy, inspector, workflows
from modules.prompts.public import known_minor_characters

from ..models import (
    GenerateResponse,
    GenerationOptions,
    ImageRequest,
    PromptingSettingsRead,
    PromptingSettingsUpdate,
)
from ..services import GenerationService, load_config, update, view

router = APIRouter(prefix="/generate", tags=["generation"])


async def get_service(request: Request, session: DbSession) -> GenerationService:
    ctx = get_context(request.app)
    return GenerationService(
        session=session,
        tenant_id=getattr(request.state, "tenant_id", None),
        comfy=comfy(ctx),
        library=workflows(ctx),
        inspector=inspector(ctx),
        minor_characters=await known_minor_characters(ctx.get("cache.client")),
        config=await load_config(session),
    )


@router.get("/options", response_model=GenerationOptions, summary="Models, LoRAs, samplers, sizes")
async def options(service: GenerationService = Depends(get_service)) -> GenerationOptions:
    return await service.options()


@router.post(
    "/image",
    response_model=GenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue text-to-image jobs",
)
async def generate_image(
    payload: ImageRequest, service: GenerationService = Depends(get_service)
) -> GenerateResponse:
    return await service.generate_image(payload)


@router.get(
    "/settings",
    response_model=PromptingSettingsRead,
    summary="Negatives per family, global negative and content policy (base + additions)",
)
async def get_settings(request: Request, session: DbSession) -> PromptingSettingsRead:
    learned = await known_minor_characters(get_context(request.app).get("cache.client"))
    return await view(session, learned_characters=learned)


@router.put(
    "/settings",
    response_model=PromptingSettingsRead,
    summary="Edit negatives and add (never remove) policy entries",
)
async def put_settings(
    payload: PromptingSettingsUpdate, request: Request, session: DbSession
) -> PromptingSettingsRead:
    await update(session, payload)
    learned = await known_minor_characters(get_context(request.app).get("cache.client"))
    return await view(session, learned_characters=learned)
