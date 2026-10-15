"""The policy as operations other modules call; the rules live in validations/."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ..validations import (
    ADULT_ANCHOR,
    MINOR_CHARACTERS,
    MINOR_NEGATIVE,
    MINOR_TERMS,
    ensure_edit_source_allowed,
    ensure_prompt_allowed,
    with_minor_negative,
)


@dataclass(frozen=True, slots=True)
class CheckedPrompt:
    positive: str
    negative: str


@dataclass(frozen=True, slots=True)
class PolicyBase:
    """The built-in lists: shown in Ajustes, never editable from there."""

    terms: tuple[str, ...]
    characters: tuple[str, ...]
    negative: str


@dataclass(frozen=True, slots=True)
class PolicyAdditions:
    """What the operator added on top of the base. Additions only tighten."""

    terms: tuple[str, ...] = ()
    characters: tuple[str, ...] = ()
    negative: str = ""


def check_prompt(
    positive: str,
    negative: str,
    *,
    adult: bool,
    extra_minor_characters: Iterable[str] = (),
    additions: PolicyAdditions | None = None,
) -> CheckedPrompt:
    """Refuse a disallowed prompt, or return it with the mandatory additions."""
    added = additions or PolicyAdditions()
    ensure_prompt_allowed(
        positive,
        adult=adult,
        extra_minor_characters=[*extra_minor_characters, *added.characters],
        extra_terms=added.terms,
    )
    return CheckedPrompt(positive=positive, negative=with_minor_negative(negative, added.negative))


def base_policy() -> PolicyBase:
    return PolicyBase(terms=MINOR_TERMS, characters=MINOR_CHARACTERS, negative=MINOR_NEGATIVE)


def check_edit_source(*, adult: bool, generated_by_app: bool) -> None:
    ensure_edit_source_allowed(adult=adult, generated_by_app=generated_by_app)


def adult_anchor() -> str:
    return ADULT_ANCHOR


def minor_negative() -> str:
    return MINOR_NEGATIVE
