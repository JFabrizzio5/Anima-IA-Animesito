"""Wire contracts for the Generation module."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MAX_SEED = 2**53 - 1


class LoraSpec(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    strength: float = Field(default=0.8, ge=-2.0, le=2.0)


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    negative: str = Field(default="", max_length=4000)
    model: str = Field(
        min_length=6, max_length=300, examples=["ckpt:waiIllustriousSDXL_v170.safetensors"]
    )
    width: int = Field(default=832, ge=256, le=2048)
    height: int = Field(default=1216, ge=256, le=2048)
    steps: int | None = Field(default=None, ge=1, le=150)
    cfg: float | None = Field(default=None, ge=0.0, le=30.0)
    sampler: str | None = Field(default=None, max_length=64)
    scheduler: str | None = Field(default=None, max_length=64)
    seed: int = Field(default=-1, ge=-1, le=MAX_SEED)
    batch_size: int = Field(default=1, ge=1, le=4)
    count: int = Field(default=1, ge=1, le=16)
    adult: bool = False
    quality_tags: bool = True
    loras: list[LoraSpec] = Field(default_factory=list, max_length=6)
    # One prompt per character, encoded separately so their traits do not
    # bleed into each other (A1111's BREAK). `prompt` holds the shared scene.
    character_prompts: list[str] = Field(default_factory=list, max_length=4)
    # blend: concatenated conditionings; columns: each character in its own
    # vertical strip, left to right.
    layout: Literal["blend", "columns"] = "blend"
    # An artistic style from styles.toml (v1's "Anime Classic" presets).
    style: str | None = Field(default=None, max_length=40)
    # Second pass at a larger size: latent upscale, then a partial re-sample.
    hires: bool = False
    hires_scale: float = Field(default=1.5, ge=1.25, le=2.0)
    hires_denoise: float = Field(default=0.45, ge=0.2, le=0.75)


class QueuedJob(BaseModel):
    id: str
    title: str
    status: str


class GenerateResponse(BaseModel):
    jobs: list[QueuedJob]
    prompt: str
    negative: str


class ModelOption(BaseModel):
    id: str
    label: str
    family: str
    family_label: str
    v_prediction: bool
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    supports_negative: bool


class LoraOption(BaseModel):
    name: str
    base_model: str | None
    trigger_words: list[str]


class SizePreset(BaseModel):
    label: str
    width: int
    height: int


class StyleOption(BaseModel):
    id: str
    group: str
    label: str
    pos: str
    neg: str
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    width: int | None
    height: int | None
    hires: bool


class GenerationOptions(BaseModel):
    models: list[ModelOption]
    loras: list[LoraOption]
    samplers: list[str]
    schedulers: list[str]
    sizes: list[SizePreset]
    styles: list[StyleOption] = []
    engine_reachable: bool


class FamilyNegative(BaseModel):
    family: str
    label: str
    default_negative: str
    default_safe_negative: str
    # None means the default above is in use.
    negative: str | None
    safe_negative: str | None


class PolicyView(BaseModel):
    """Base lists are read-only; only the extra_* fields can be edited."""

    base_terms: list[str]
    base_characters: list[str]
    base_negative: str
    learned_characters: list[str]
    extra_terms: list[str]
    extra_characters: list[str]
    extra_negative: str


class PromptingSettingsRead(BaseModel):
    global_negative: str
    families: list[FamilyNegative]
    policy: PolicyView


class FamilyNegativeUpdate(BaseModel):
    negative: str | None = Field(default=None, max_length=2000)
    safe_negative: str | None = Field(default=None, max_length=2000)


class PromptingSettingsUpdate(BaseModel):
    global_negative: str | None = Field(default=None, max_length=2000)
    family_negatives: dict[str, FamilyNegativeUpdate] | None = None
    extra_terms: list[str] | None = Field(default=None, max_length=300)
    extra_characters: list[str] | None = Field(default=None, max_length=300)
    extra_negative: str | None = Field(default=None, max_length=2000)
