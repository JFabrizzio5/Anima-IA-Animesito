"""HTTP layer for the Assistant module."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Request

from jfastframework.app import get_context
from jfastframework.errors import ServiceUnavailableError, ValidationError
from jfastframework.plugins.builtin.database import DbSession

from modules.engine.public import ComfyError, comfy
from modules.generation.public import policy_additions
from modules.prompts.public import known_minor_characters

from ..models import EnhanceRequest, EnhanceResponse, LlmModelOut, LlmModels
from ..services import AssistantConfig, EnhanceError, OllamaClient, OllamaUnavailable, enhance

router = APIRouter(prefix="/assistant", tags=["assistant"])


def _deps(request: Request) -> tuple[OllamaClient, AssistantConfig]:
    ctx = get_context(request.app)
    return ctx.require("ollama", OllamaClient), ctx.require("assistant.config", AssistantConfig)


async def free_comfy_if_idle(request: Request) -> None:
    """Give the LLM the whole card when ComfyUI has nothing to render.

    With an SDXL checkpoint resident (~7 GB of 12) an 8B model only partly
    fits and runs several times slower on the CPU. Reloading the checkpoint
    for the next render costs a few seconds; a half-offloaded LLM costs more.
    """
    client = comfy(get_context(request.app))
    with contextlib.suppress(ComfyError):
        running, pending = await client.queue_depth()
        if running == 0 and pending == 0:
            await client.free(unload_models=True, free_memory=True)


@router.get("/models", response_model=LlmModels, summary="Ollama models that fit the GPU")
async def models(request: Request) -> LlmModels:
    client, config = _deps(request)
    default = config.default_model
    try:
        found = await client.models()
    except OllamaUnavailable:
        return LlmModels(models=[], reachable=False, default=default)
    usable = [
        model
        for model in found
        if not model.is_embedding
        and not model.is_reasoning
        and model.size_gb <= config.max_model_gb
    ]
    return LlmModels(
        models=[
            LlmModelOut(
                name=model.name,
                size_gb=model.size_gb,
                parameter_size=model.parameter_size,
                default=model.name == default,
            )
            for model in usable
        ],
        reachable=True,
        default=default,
    )


@router.post("/enhance", response_model=EnhanceResponse, summary="Description to Danbooru tags")
async def enhance_prompt(
    payload: EnhanceRequest, request: Request, session: DbSession
) -> EnhanceResponse:
    client, config = _deps(request)
    ctx = get_context(request.app)
    await free_comfy_if_idle(request)
    try:
        result = await enhance(
            client,
            model=payload.model or config.default_model,
            prompt=payload.prompt,
            adult=payload.adult,
            keep_alive=config.keep_alive,
            extra_minor_characters=await known_minor_characters(ctx.get("cache.client")),
            additions=await policy_additions(session),
        )
    except OllamaUnavailable as exc:
        raise ServiceUnavailableError(f"Ollama no responde: {exc}") from exc
    except EnhanceError as exc:
        raise ValidationError(f"El modelo no devolvió tags utilizables: {exc}") from exc
    return EnhanceResponse(
        prompt=result.prompt, negative=result.negative, model=result.model, seconds=result.seconds
    )
