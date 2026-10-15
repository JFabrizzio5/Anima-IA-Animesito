"""Turn a resolved request into the ComfyUI graph for one job (one batch)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from modules.engine.public import (
    Graph,
    LoraRef,
    Ref,
    WorkflowLibrary,
    add_node,
    insert_lora_chain,
    insert_v_prediction,
    node_id,
    ref,
    rewire,
    set_inputs,
)

from .profiles import ModelChoice


@dataclass(frozen=True, slots=True)
class Sampling:
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    seed: int
    batch_size: int


def output_prefix(now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    return f"animesito/{moment:%Y-%m-%d}/img"


def build_txt2img(
    library: WorkflowLibrary,
    model: ModelChoice,
    *,
    positive: str,
    negative: str,
    sampling: Sampling,
    loras: Sequence[LoraRef],
    characters: Sequence[str] = (),
    layout: str = "blend",
    hires: Hires | None = None,
) -> Graph:
    if model.profile.is_flux:
        # T5 reads sentences, not 75-token chunks: one prompt carries everyone.
        text = ", ".join([positive, *characters]) if characters else positive
        return _flux(library, model, positive=text, sampling=sampling, loras=loras)
    return _sdxl(
        library,
        model,
        positive=positive,
        negative=negative,
        sampling=sampling,
        loras=loras,
        characters=characters,
        layout=layout,
        hires=hires,
    )


def _sdxl(
    library: WorkflowLibrary,
    model: ModelChoice,
    *,
    positive: str,
    negative: str,
    sampling: Sampling,
    loras: Sequence[LoraRef],
    characters: Sequence[str] = (),
    layout: str = "blend",
    hires: Hires | None = None,
) -> Graph:
    graph = library.load(model.profile.workflow)
    set_inputs(graph, "@ckpt", ckpt_name=model.filename)
    set_inputs(graph, "@positive", text=positive)
    set_inputs(graph, "@negative", text=negative)
    set_inputs(
        graph,
        "@latent",
        width=sampling.width,
        height=sampling.height,
        batch_size=sampling.batch_size,
    )
    set_inputs(
        graph,
        "@sampler",
        seed=sampling.seed,
        steps=sampling.steps,
        cfg=sampling.cfg,
        sampler_name=sampling.sampler,
        scheduler=sampling.scheduler,
        denoise=1.0,
    )
    set_inputs(graph, "@save", filename_prefix=output_prefix())
    ckpt = node_id(graph, "@ckpt")
    model_ref, clip_ref = insert_lora_chain(graph, loras, model=ref(ckpt, 0), clip=ref(ckpt, 1))
    if model.v_prediction:
        insert_v_prediction(graph, model=model_ref)
    if characters and clip_ref is not None:
        add_characters(graph, characters, clip=clip_ref, layout=layout, sampling=sampling)
    if hires is not None:
        add_hires_pass(graph, hires, sampling=sampling)
    return graph


@dataclass(frozen=True, slots=True)
class Hires:
    scale: float = 1.5
    denoise: float = 0.45


def add_hires_pass(graph: Graph, hires: Hires, *, sampling: Sampling) -> None:
    """A1111's hires fix: upscale the latent, re-sample part of the way down.

    Runs last, so the second sampler inherits whatever the first one reads by
    then -- LoRAs, v-prediction, per-character conditioning. ComfyUI's
    VAEDecode falls back to tiles on its own if the larger decode runs out of
    VRAM.
    """
    first = node_id(graph, "@sampler")
    upscaled = add_node(
        graph,
        "LatentUpscaleBy",
        {"samples": ref(first, 0), "upscale_method": "nearest-exact", "scale_by": hires.scale},
    )
    inputs = graph[first]["inputs"]
    second = add_node(
        graph,
        "KSampler",
        {
            "model": inputs["model"],
            "positive": inputs["positive"],
            "negative": inputs["negative"],
            "latent_image": ref(upscaled, 0),
            "seed": sampling.seed,
            "steps": max(8, round(sampling.steps * 0.6)),
            "cfg": sampling.cfg,
            "sampler_name": sampling.sampler,
            "scheduler": sampling.scheduler,
            "denoise": hires.denoise,
        },
        title="@hires_sampler",
    )
    rewire(graph, ref(first, 0), ref(second, 0), skip=(upscaled, second))


def add_characters(
    graph: Graph, characters: Sequence[str], *, clip: Ref, layout: str, sampling: Sampling
) -> None:
    """Encode each character on its own and feed the sampler their union.

    ``blend`` concatenates the conditionings (BREAK): every character gets its
    own 77-token window, which is most of what stops one girl's hair colour
    landing on the other. ``columns`` also pins each character to a vertical
    strip of the image, left to right, on top of the full-frame scene prompt.
    """
    positive = node_id(graph, "@positive")
    conditioning = ref(positive, 0)
    count = len(characters)
    strip = max(64, (sampling.width // count) // 8 * 8)
    for index, text in enumerate(characters):
        encoded = add_node(graph, "CLIPTextEncode", {"text": text, "clip": list(clip)})
        if layout == "columns":
            area = add_node(
                graph,
                "ConditioningSetArea",
                {
                    "conditioning": ref(encoded, 0),
                    "width": strip,
                    "height": sampling.height,
                    "x": min(index * strip, sampling.width - strip),
                    "y": 0,
                    "strength": 1.0,
                },
            )
            joined = add_node(
                graph,
                "ConditioningCombine",
                {"conditioning_1": conditioning, "conditioning_2": ref(area, 0)},
            )
        else:
            joined = add_node(
                graph,
                "ConditioningConcat",
                {"conditioning_to": conditioning, "conditioning_from": ref(encoded, 0)},
            )
        conditioning = ref(joined, 0)
    set_inputs(graph, "@sampler", positive=conditioning)


def _flux(
    library: WorkflowLibrary,
    model: ModelChoice,
    *,
    positive: str,
    sampling: Sampling,
    loras: Sequence[LoraRef],
) -> Graph:
    graph = library.load(model.profile.workflow)
    set_inputs(graph, "@unet", unet_name=model.filename)
    set_inputs(graph, "@positive", text=positive)
    # Flux is guidance-distilled: "cfg" in the request is FluxGuidance.
    set_inputs(graph, "@guidance", guidance=sampling.cfg)
    set_inputs(
        graph,
        "@latent",
        width=sampling.width,
        height=sampling.height,
        batch_size=sampling.batch_size,
    )
    set_inputs(graph, "@model_sampling", width=sampling.width, height=sampling.height)
    set_inputs(graph, "@scheduler", steps=sampling.steps, scheduler=sampling.scheduler, denoise=1.0)
    set_inputs(graph, "@sampler_select", sampler_name=sampling.sampler)
    set_inputs(graph, "@noise", noise_seed=sampling.seed)
    set_inputs(graph, "@save", filename_prefix=output_prefix())
    unet = node_id(graph, "@unet")
    insert_lora_chain(graph, loras, model=ref(unet, 0), clip=None)
    return graph
