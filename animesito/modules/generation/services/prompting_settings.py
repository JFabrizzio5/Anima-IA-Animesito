"""The operator-editable side of prompting: negatives and policy additions.

Stored through the settings module; validated here, where the families live.
Policy additions only tighten -- the base lists in modules/policy are shown
read-only and cannot be shortened from the UI.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from jfastframework.errors import ValidationError

from modules.policy.public import PolicyAdditions, base_policy
from modules.settings.public import read_settings, write_settings

from ..models import (
    FamilyNegative,
    PolicyView,
    PromptingSettingsRead,
    PromptingSettingsUpdate,
)
from .profiles import PROFILES

GLOBAL_NEGATIVE = "prompting.global_negative"
FAMILY_NEGATIVES = "prompting.family_negatives"
EXTRA_TERMS = "policy.extra_terms"
EXTRA_CHARACTERS = "policy.extra_characters"
EXTRA_NEGATIVE = "policy.extra_negative"
KEYS = [GLOBAL_NEGATIVE, FAMILY_NEGATIVES, EXTRA_TERMS, EXTRA_CHARACTERS, EXTRA_NEGATIVE]

MAX_ENTRIES = 300
MAX_ENTRY = 60


@dataclass(frozen=True, slots=True)
class PromptingConfig:
    global_negative: str = ""
    # family -> {"negative": str | None, "safe_negative": str | None}; None = default
    family_negatives: dict[str, dict[str, str | None]] = field(default_factory=dict)
    additions: PolicyAdditions = field(default_factory=PolicyAdditions)

    def negative_for(self, family: str) -> str | None:
        return self.family_negatives.get(family, {}).get("negative")

    def safe_negative_for(self, family: str) -> str | None:
        return self.family_negatives.get(family, {}).get("safe_negative")


def _clean_list(values: Iterable[str], *, already: Iterable[str]) -> list[str]:
    base = {item.lower() for item in already}
    cleaned: dict[str, None] = {}
    for raw in values:
        entry = " ".join(raw.replace("_", " ").lower().split())
        if not entry:
            continue
        if len(entry) < 2 or len(entry) > MAX_ENTRY:
            raise ValidationError(f"{raw!r}: each entry must be 2 to {MAX_ENTRY} characters")
        if entry not in base:
            cleaned.setdefault(entry, None)
    if len(cleaned) > MAX_ENTRIES:
        raise ValidationError(f"At most {MAX_ENTRIES} additions per list")
    return list(cleaned)


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_list(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


async def load_config(session: Any) -> PromptingConfig:
    raw = await read_settings(session, KEYS)
    families = raw.get(FAMILY_NEGATIVES)
    return PromptingConfig(
        global_negative=_as_str(raw.get(GLOBAL_NEGATIVE)),
        family_negatives=families if isinstance(families, dict) else {},
        additions=PolicyAdditions(
            terms=_as_list(raw.get(EXTRA_TERMS)),
            characters=_as_list(raw.get(EXTRA_CHARACTERS)),
            negative=_as_str(raw.get(EXTRA_NEGATIVE)),
        ),
    )


async def view(session: Any, *, learned_characters: Iterable[str]) -> PromptingSettingsRead:
    config = await load_config(session)
    base = base_policy()
    return PromptingSettingsRead(
        global_negative=config.global_negative,
        families=[
            FamilyNegative(
                family=name,
                label=profile.label,
                default_negative=profile.negative,
                default_safe_negative=profile.safe_negative,
                negative=config.negative_for(name),
                safe_negative=config.safe_negative_for(name),
            )
            for name, profile in PROFILES.items()
        ],
        policy=PolicyView(
            base_terms=list(base.terms),
            base_characters=list(base.characters),
            base_negative=base.negative,
            learned_characters=sorted(learned_characters),
            extra_terms=list(config.additions.terms),
            extra_characters=list(config.additions.characters),
            extra_negative=config.additions.negative,
        ),
    )


async def update(session: Any, payload: PromptingSettingsUpdate) -> None:
    base = base_policy()
    values: dict[str, Any] = {}
    if payload.global_negative is not None:
        values[GLOBAL_NEGATIVE] = payload.global_negative.strip()
    if payload.family_negatives is not None:
        unknown = set(payload.family_negatives) - set(PROFILES)
        if unknown:
            raise ValidationError(f"Unknown model families: {', '.join(sorted(unknown))}")
        values[FAMILY_NEGATIVES] = {
            family: {
                # An empty box means "back to the default", not "no negative".
                "negative": (item.negative or "").strip() or None,
                "safe_negative": (item.safe_negative or "").strip() or None,
            }
            for family, item in payload.family_negatives.items()
        }
    if payload.extra_terms is not None:
        values[EXTRA_TERMS] = _clean_list(payload.extra_terms, already=base.terms)
    if payload.extra_characters is not None:
        values[EXTRA_CHARACTERS] = _clean_list(payload.extra_characters, already=base.characters)
    if payload.extra_negative is not None:
        values[EXTRA_NEGATIVE] = payload.extra_negative.strip()
    await write_settings(session, values)
