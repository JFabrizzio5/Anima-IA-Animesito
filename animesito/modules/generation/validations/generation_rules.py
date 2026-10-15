"""Rules a schema cannot express for a generation request. Pure functions."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from jfastframework.errors import ValidationError

from ..models import ImageRequest, LoraSpec

#: Latent space is 1/8 of pixel space; SDXL also wants multiples of 64 to
#: stay on its training buckets, but 8 is the hard requirement.
DIMENSION_STEP = 8
#: Above this many pixels per image SDXL draws duplicated limbs and 12 GB of
#: VRAM runs out on a batch of 4.
MAX_PIXELS = 1536 * 1536


def ensure_dimensions(request: ImageRequest) -> None:
    for name, value in (("width", request.width), ("height", request.height)):
        if value % DIMENSION_STEP:
            raise ValidationError(f"{name} must be a multiple of {DIMENSION_STEP}, not {value}")
    if request.width * request.height > MAX_PIXELS:
        raise ValidationError(
            f"{request.width}x{request.height} is too large; generate smaller and upscale"
        )


MAX_CHARACTER_PROMPT = 1000


def ensure_character_prompts(prompts: Sequence[str]) -> None:
    for index, text in enumerate(prompts, start=1):
        if not text.strip():
            raise ValidationError(f"Character {index} has an empty prompt")
        if len(text) > MAX_CHARACTER_PROMPT:
            raise ValidationError(
                f"Character {index} prompt is longer than {MAX_CHARACTER_PROMPT} characters"
            )


def ensure_model_installed(model_id: str, installed: Collection[str]) -> None:
    if model_id not in installed:
        raise ValidationError(f"Model {model_id!r} is not installed in ComfyUI or is not supported")


def ensure_loras_installed(loras: Sequence[LoraSpec], installed: Collection[str]) -> None:
    missing = [lora.name for lora in loras if lora.name not in installed]
    if missing:
        raise ValidationError(f"LoRA not installed in ComfyUI: {', '.join(missing)}")


def ensure_choice(kind: str, value: str | None, allowed: Collection[str]) -> None:
    if value is not None and allowed and value not in allowed:
        raise ValidationError(f"Unknown {kind} {value!r}")
