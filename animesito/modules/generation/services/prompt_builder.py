"""Compose the prompt a family expects from what the user typed.

Order matters for booru-tag models: quality first, then rating, then subject.
The policy module has the last word and adds its minor-safety negative.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from modules.policy.public import PolicyAdditions, adult_anchor, check_prompt

from .profiles import Profile
from .styles import Style


@dataclass(frozen=True, slots=True)
class ComposedPrompt:
    positive: str
    negative: str


def join_tags(*parts: str) -> str:
    cleaned = [part.strip().strip(",").strip() for part in parts]
    return ", ".join(part for part in cleaned if part)


def compose(
    profile: Profile,
    *,
    prompt: str,
    negative: str,
    adult: bool,
    quality_tags: bool,
    extra_minor_characters: Iterable[str] = (),
    negative_override: str | None = None,
    safe_negative_override: str | None = None,
    global_negative: str = "",
    additions: PolicyAdditions | None = None,
    style: Style | None = None,
) -> ComposedPrompt:
    rating = join_tags(adult_anchor(), profile.adult_tags) if adult else profile.safe_tags
    # A style brings its own quality tags and replaces the family's (v1 did
    # the same: style text first, then the user's prompt).
    quality = style.pos if style else profile.quality
    positive = join_tags(quality if quality_tags else "", rating, prompt)
    family_negative = profile.negative if negative_override is None else negative_override
    if style is not None:
        # The style's negative replaces the family default; an operator
        # override from Ajustes is required text and stays.
        family_negative = join_tags(
            style.neg, "" if negative_override is None else negative_override
        )
    if style is not None:
        # The style's negative replaces the family default; an operator
        # override from Ajustes is required text and stays.
        family_negative = join_tags(
            style.neg, "" if negative_override is None else negative_override
        )
    safe_negative = (
        profile.safe_negative if safe_negative_override is None else safe_negative_override
    )
    base_negative = join_tags(
        family_negative if quality_tags else "",
        "" if adult else safe_negative,
        global_negative,
        negative,
    )
    checked = check_prompt(
        positive,
        base_negative,
        adult=adult,
        extra_minor_characters=extra_minor_characters,
        additions=additions,
    )
    return ComposedPrompt(positive=checked.positive, negative=checked.negative)
