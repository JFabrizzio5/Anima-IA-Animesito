from __future__ import annotations

import pytest

from jfastframework.errors import ValidationError

from modules.policy.public import check_edit_source, check_prompt
from modules.policy.validations import (
    MINOR_CHARACTERS,
    MINOR_NEGATIVE,
    MINOR_TERMS,
    find_minor_characters,
    find_minor_terms,
    normalise,
)

# A floor, not a snapshot: the lists may grow, never shrink. On 2026-10-09 an
# editor agent emptied them by accident and adult mode stopped refusing minors;
# this is what turns that into a red build instead of a silent hole.
REQUIRED_TERMS = {"loli", "shota", "child", "kid", "underage", "teen", "school uniform"}
REQUIRED_CHARACTERS = {"uraraka ochako", "hayase nagatoro", "kitagawa marin", "nakano miku"}


def test_policy_lists_were_not_cut() -> None:
    assert set(MINOR_TERMS) >= REQUIRED_TERMS, "MINOR_TERMS lost entries: restore policy_rules.py"
    assert set(MINOR_CHARACTERS) >= REQUIRED_CHARACTERS, "MINOR_CHARACTERS lost entries"
    assert len(MINOR_TERMS) >= 38 and len(MINOR_CHARACTERS) >= 20
    for term in ("child", "loli", "shota", "underage"):
        assert term in MINOR_NEGATIVE


def test_normalise_collapses_booru_separators_and_weights() -> None:
    assert normalise("(Uraraka_Ochako:1.2), 1girl") == " uraraka ochako 1girl "


@pytest.mark.parametrize(
    "prompt",
    [
        "1girl, loli, nude",
        "1girl, (school_uniform:1.1), nsfw",
        "young girl, lingerie",
        "1girl, teenager, bedroom",
    ],
)
def test_adult_mode_refuses_minor_terms(prompt: str) -> None:
    with pytest.raises(ValidationError):
        check_prompt(prompt, "", adult=True)


@pytest.mark.parametrize(
    "prompt",
    [
        "1girl, uraraka_ochako, boku no hero academia",
        "1girl, ochako uraraka",
        "nakano miku, headphones",
        "(hatsune miku:1.3)",
    ],
)
def test_adult_mode_refuses_canonically_minor_characters(prompt: str) -> None:
    with pytest.raises(ValidationError):
        check_prompt(prompt, "", adult=True)


def test_safe_mode_allows_the_same_prompt() -> None:
    checked = check_prompt("1girl, uraraka ochako, school uniform, smiling", "", adult=False)
    assert checked.positive.startswith("1girl")


@pytest.mark.parametrize("text", ["kidney", "skidding", "nineteen", "minority report"])
def test_whole_words_only(text: str) -> None:
    assert find_minor_terms(text) == []


def test_adult_character_passes() -> None:
    assert find_minor_characters("1girl, tifa lockhart, final fantasy vii") == []


def test_minor_negative_is_always_prepended() -> None:
    checked = check_prompt("1girl, smiling", "lowres, bad hands", adult=False)
    assert checked.negative.startswith(MINOR_NEGATIVE)
    assert checked.negative.endswith("lowres, bad hands")
    assert check_prompt("1girl", "", adult=False).negative == MINOR_NEGATIVE


def test_adult_edit_needs_app_provenance() -> None:
    with pytest.raises(ValidationError):
        check_edit_source(adult=True, generated_by_app=False)
    check_edit_source(adult=True, generated_by_app=True)
    check_edit_source(adult=False, generated_by_app=False)
