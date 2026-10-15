"""Business logic for the Generation module: request in, queued jobs out."""

from __future__ import annotations

import math
import random
from collections.abc import Collection
from typing import Any

from jfastframework.errors import ServiceUnavailableError, ValidationError

from modules.engine.public import (
    ComfyClient,
    ComfyError,
    LoraRef,
    ModelInspector,
    ModelTraits,
    WorkflowLibrary,
)
from modules.jobs.public import NewJob, enqueue
from shared.enums import JobKind

from ..models import (
    MAX_SEED,
    GenerateResponse,
    GenerationOptions,
    ImageRequest,
    LoraOption,
    ModelOption,
    QueuedJob,
    SizePreset,
    StyleOption,
)
from ..validations import (
    ensure_character_prompts,
    ensure_choice,
    ensure_dimensions,
    ensure_loras_installed,
    ensure_model_installed,
)
from .graph_builder import Hires, Sampling, build_txt2img
from .profiles import CKPT, GGUF, ModelChoice, resolve
from .prompt_builder import compose, join_tags
from .prompting_settings import PromptingConfig
from .styles import STYLES

SIZE_PRESETS: tuple[SizePreset, ...] = (
    SizePreset(label="Retrato 2:3", width=832, height=1216),
    SizePreset(label="Cuadrado", width=1024, height=1024),
    SizePreset(label="Paisaje 3:2", width=1216, height=832),
    SizePreset(label="Retrato alto 9:16", width=768, height=1344),
    SizePreset(label="Panorámico 16:9", width=1344, height=768),
    SizePreset(label="Retrato 4:5", width=896, height=1152),
)

_LOADERS: dict[str, tuple[str, str, str]] = {
    # loader prefix -> (ComfyUI node, input name, models subfolder)
    CKPT: ("CheckpointLoaderSimple", "ckpt_name", "checkpoints"),
    GGUF: ("UnetLoaderGGUF", "unet_name", "diffusion_models"),
}


def vars_of(style: Any) -> dict[str, Any]:
    return {name: getattr(style, name) for name in style.__slots__}


def _label(filename: str) -> str:
    stem = filename.rsplit("/", 1)[-1]
    for suffix in (".safetensors", ".gguf", ".ckpt"):
        stem = stem.removesuffix(suffix)
    return stem


class GenerationService:
    def __init__(
        self,
        *,
        session: Any,
        tenant_id: str | None,
        comfy: ComfyClient,
        library: WorkflowLibrary,
        inspector: ModelInspector,
        rng: random.Random | None = None,
        minor_characters: Collection[str] = (),
        config: PromptingConfig | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.comfy = comfy
        self.library = library
        self.inspector = inspector
        self.rng = rng or random.SystemRandom()
        # Learned from AniList ages by the prompts module; the policy refuses
        # them in adult mode on top of its static list.
        self.minor_characters = minor_characters
        # Operator-edited negatives and policy additions (Ajustes).
        self.config = config or PromptingConfig()

    async def _choices(self, node: str, field: str) -> list[str]:
        try:
            return await self.comfy.choices(node, field)
        except ComfyError as exc:
            raise ServiceUnavailableError(f"ComfyUI is not available: {exc}") from exc

    async def installed_models(self) -> dict[str, ModelChoice]:
        found: dict[str, ModelChoice] = {}
        for loader, (node, field, folder) in _LOADERS.items():
            for filename in await self._choices(node, field):
                traits = (
                    await self.inspector.traits(folder, filename)
                    if loader == CKPT
                    else ModelTraits()
                )
                choice = resolve(loader, filename, traits)
                if choice is not None:
                    found[choice.id] = choice
        return found

    async def options(self) -> GenerationOptions:
        try:
            models = await self.installed_models()
            lora_names = await self._choices("LoraLoader", "lora_name")
            samplers = await self._choices("KSampler", "sampler_name")
            schedulers = await self._choices("KSampler", "scheduler")
        except ServiceUnavailableError:
            return GenerationOptions(
                models=[],
                loras=[],
                samplers=[],
                schedulers=[],
                sizes=list(SIZE_PRESETS),
                engine_reachable=False,
            )
        loras = []
        for name in lora_names:
            traits = await self.inspector.traits("loras", name)
            loras.append(
                LoraOption(
                    name=name,
                    base_model=traits.base_model,
                    trigger_words=list(traits.trigger_words),
                )
            )
        return GenerationOptions(
            models=[
                ModelOption(
                    id=choice.id,
                    label=_label(choice.filename),
                    family=choice.profile.family,
                    family_label=choice.profile.label,
                    v_prediction=choice.v_prediction,
                    steps=choice.profile.steps,
                    cfg=choice.profile.cfg,
                    sampler=choice.profile.sampler,
                    scheduler=choice.profile.scheduler,
                    supports_negative=not choice.profile.is_flux,
                )
                for choice in sorted(models.values(), key=lambda item: item.id.lower())
            ],
            loras=loras,
            samplers=samplers,
            schedulers=schedulers,
            sizes=list(SIZE_PRESETS),
            styles=[StyleOption(**vars_of(style)) for style in STYLES.values()],
            engine_reachable=True,
        )

    async def generate_image(self, request: ImageRequest) -> GenerateResponse:
        ensure_dimensions(request)
        ensure_character_prompts(request.character_prompts)
        models = await self.installed_models()
        ensure_model_installed(request.model, models)
        choice = models[request.model]
        profile = choice.profile
        style = None
        if request.style:
            style = STYLES.get(request.style)
            if style is None:
                raise ValidationError(f"Unknown style {request.style!r}")
        lora_names = set(await self._choices("LoraLoader", "lora_name"))
        ensure_loras_installed(request.loras, lora_names)
        if not profile.is_flux:
            ensure_choice(
                "sampler", request.sampler, await self._choices("KSampler", "sampler_name")
            )
            ensure_choice(
                "scheduler", request.scheduler, await self._choices("KSampler", "scheduler")
            )

        characters = [text.strip() for text in request.character_prompts]
        # The policy reads everything that will reach the model, characters
        # included; the scene alone is what the graph's main prompt carries.
        composed = compose(
            profile,
            prompt=join_tags(request.prompt, *characters),
            negative=request.negative,
            adult=request.adult,
            quality_tags=request.quality_tags,
            extra_minor_characters=self.minor_characters,
            negative_override=self.config.negative_for(profile.family),
            safe_negative_override=self.config.safe_negative_for(profile.family),
            global_negative=self.config.global_negative,
            additions=self.config.additions,
            style=style,
        )
        scene = (
            compose(
                profile,
                prompt=request.prompt,
                negative=request.negative,
                adult=request.adult,
                quality_tags=request.quality_tags,
                extra_minor_characters=self.minor_characters,
                negative_override=self.config.negative_for(profile.family),
                safe_negative_override=self.config.safe_negative_for(profile.family),
                global_negative=self.config.global_negative,
                additions=self.config.additions,
                style=style,
            )
            if characters
            else composed
        )
        loras = [LoraRef(item.name, item.strength, item.strength) for item in request.loras]
        if (
            request.adult
            and profile.adult_lora
            and profile.adult_lora in lora_names
            and all(item.name != profile.adult_lora for item in loras)
        ):
            loras.append(LoraRef(profile.adult_lora, profile.adult_lora_strength))

        steps = request.steps or profile.steps
        cfg = request.cfg if request.cfg is not None else profile.cfg
        sampler = request.sampler or profile.sampler
        scheduler = request.scheduler or profile.scheduler
        base_seed = request.seed if request.seed >= 0 else self.rng.randrange(MAX_SEED)
        negative = "" if profile.is_flux else composed.negative

        queued: list[QueuedJob] = []
        for index in range(math.ceil(request.count / request.batch_size)):
            batch = min(request.batch_size, request.count - index * request.batch_size)
            seed = (base_seed + index * request.batch_size) % MAX_SEED
            sampling = Sampling(
                width=request.width,
                height=request.height,
                steps=steps,
                cfg=cfg,
                sampler=sampler,
                scheduler=scheduler,
                seed=seed,
                batch_size=batch,
            )
            graph = build_txt2img(
                self.library,
                choice,
                positive=scene.positive,
                negative=negative,
                sampling=sampling,
                loras=loras,
                characters=characters,
                layout=request.layout,
                hires=Hires(request.hires_scale, request.hires_denoise) if request.hires else None,
            )
            params: dict[str, Any] = {
                "mode": "txt2img",
                "prompt": composed.positive,
                "negative": negative,
                "user_prompt": request.prompt,
                "user_negative": request.negative,
                "character_prompts": characters,
                "layout": request.layout,
                "style": request.style,
                "hires": request.hires,
                "hires_scale": request.hires_scale,
                "hires_denoise": request.hires_denoise,
                "model": choice.id,
                "family": profile.family,
                "v_prediction": choice.v_prediction,
                "seed": seed,
                "width": request.width,
                "height": request.height,
                "steps": steps,
                "cfg": cfg,
                "sampler": sampler,
                "scheduler": scheduler,
                "batch_size": batch,
                "adult": request.adult,
                "quality_tags": request.quality_tags,
                "loras": [{"name": lora.name, "strength": lora.strength_model} for lora in loras],
            }
            summary = await enqueue(
                self.session,
                tenant_id=self.tenant_id,
                new=NewJob(
                    kind=JobKind.IMAGE,
                    title=f"{_label(choice.filename)} · {request.width}x{request.height} · {seed}",
                    workflow=profile.workflow,
                    graph=graph,
                    params=params,
                ),
            )
            queued.append(QueuedJob(id=summary.id, title=summary.title, status=summary.status))
        return GenerateResponse(jobs=queued, prompt=composed.positive, negative=negative)
