"""Model families: which one a file belongs to, and how that family is driven."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.engine.public import ModelTraits

PROFILES_FILE = Path(__file__).resolve().parent.parent / "profiles.toml"

CKPT = "ckpt"
GGUF = "gguf"


@dataclass(frozen=True, slots=True)
class Profile:
    family: str
    label: str
    workflow: str
    quality: str
    negative: str
    adult_tags: str
    safe_tags: str
    safe_negative: str
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    adult_lora: str | None = None
    adult_lora_strength: float = 1.0

    @property
    def is_flux(self) -> bool:
        return self.workflow.startswith("flux")


def _load(path: Path = PROFILES_FILE) -> dict[str, Profile]:
    raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    return {
        name: Profile(family=name, **values) for name, values in raw.get("families", {}).items()
    }


PROFILES: dict[str, Profile] = _load()

# Not text-to-image models we drive, whatever loader lists them. redcraft/krea
# are a DiT that is neither SDXL nor Flux; listed so they stay out even when the
# models folder is not readable and the header cannot say so.
_EXCLUDED = re.compile(
    r"svd|wan2|wan_|kontext|ltx|hunyuan|i2v|t2v|refiner|inpaint|redcraft|krea", re.I
)
_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"waireal|realcn", re.I), "pony_real"),
    (re.compile(r"pony|autismmix", re.I), "pony"),
    (re.compile(r"noob", re.I), "noobai"),
    (re.compile(r"animagine", re.I), "animagine"),
    (re.compile(r"illustrious|^wai|kohaku", re.I), "illustrious"),
    (re.compile(r"realvis|juggernaut|dreamshaper|realistic|photon|epicreal", re.I), "realistic"),
)


@dataclass(frozen=True, slots=True)
class ModelChoice:
    id: str
    loader: str
    filename: str
    profile: Profile
    v_prediction: bool


def parse_model_id(model_id: str) -> tuple[str, str]:
    loader, _, filename = model_id.partition(":")
    return loader, filename


def detect_family(loader: str, filename: str, traits: ModelTraits) -> str | None:
    """The family of a model file, or None when it is not a txt2img model we drive."""
    if _EXCLUDED.search(filename):
        return None
    if loader == GGUF:
        return "flux" if "flux" in filename.lower() else None
    if traits.readable and traits.architecture not in (None, "sdxl"):
        # A Flux all-in-one checkpoint or something newer needs its own
        # workflow; SD 1.5 is not worth one in 2026.
        return None
    if traits.readable and traits.architecture is None:
        return None
    for pattern, family in _RULES:
        if pattern.search(filename):
            return family
    return "anime_sdxl"


def resolve(loader: str, filename: str, traits: ModelTraits) -> ModelChoice | None:
    family = detect_family(loader, filename, traits)
    if family is None:
        return None
    return ModelChoice(
        id=f"{loader}:{filename}",
        loader=loader,
        filename=filename,
        profile=PROFILES[family],
        v_prediction=traits.v_prediction,
    )
