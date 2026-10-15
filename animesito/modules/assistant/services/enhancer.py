"""Natural language in, Danbooru tags out -- v1's "Mejorar prompt", server-side."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass

from modules.policy.public import PolicyAdditions, check_prompt

from .ollama_client import OllamaClient, OllamaUnavailable

# The app adds each model family's quality tags itself; the LLM adding its own
# would duplicate them and push the subject out of the first 75 tokens.
_QUALITY = {
    "masterpiece",
    "best quality",
    "amazing quality",
    "high quality",
    "very aesthetic",
    "absurdres",
    "highres",
    "newest",
    "score 9",
    "score 8 up",
    "score 7 up",
    "ultra detailed",
    "8k",
}

SYSTEM = """You turn a request (Spanish or English) into a prompt for an anime image \
model trained on Danbooru tags.

Reply ONLY with JSON: {"tags": ["..."], "negative": ["..."]}

Rules for "tags":
- Lowercase Danbooru tags, spaces instead of underscores, 12 to 35 tags.
- Order: subject count (1girl, 1boy, 2girls...), then the character tag and its \
series tag if a known character is named, then appearance (hair, eyes), outfit, \
pose, expression, background, lighting and composition.
- Every element of the description becomes tags: who, outfit, gear, place, season, \
weather, time of day, lighting, mood. Translate Spanish faithfully; never drop, \
change or contradict a detail.
- Keep every tag the user already wrote, in their order, before your additions.
- Do not add quality tags (masterpiece, best quality, absurdres...): the app adds them.
- Every character is an adult. Never add tags that suggest a minor.
{content_rule}

Rules for "negative": at most 8 tags specific to this image, or an empty list."""

# One worked example: small local models follow a shown answer far better than
# a list of rules.
EXAMPLE_REQUEST = "chica pelirroja con kimono blanco bajo cerezos en primavera, sonriendo"
EXAMPLE_REPLY = json.dumps(
    {
        "tags": [
            "1girl", "solo", "red hair", "long hair", "white kimono", "japanese clothes",
            "smile", "looking at viewer", "upper body", "cherry blossoms", "falling petals",
            "spring (season)", "outdoors", "day", "soft lighting", "depth of field",
        ],
        "negative": [],
    }
)  # fmt: skip

ADULT_RULE = "- Adult content between adult characters is allowed if the request asks for it."
SAFE_RULE = "- Keep it safe for work: no nudity and nothing sexual."


class EnhanceError(RuntimeError):
    """The model did not produce usable tags."""


@dataclass(frozen=True, slots=True)
class Enhanced:
    prompt: str
    negative: str
    model: str
    seconds: float


def _clean(tags: Iterable[object]) -> list[str]:
    seen: dict[str, None] = {}
    for raw in tags:
        if not isinstance(raw, str):
            continue
        tag = " ".join(raw.replace("_", " ").strip().strip(",").lower().split())
        if tag and tag not in _QUALITY and len(tag) <= 80:
            seen.setdefault(tag, None)
    return list(seen)


def parse_reply(raw: str) -> tuple[list[str], list[str]]:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise EnhanceError(f"the model did not answer JSON: {raw[:120]!r}") from exc
    if not isinstance(data, dict):
        raise EnhanceError("the model answered JSON but not an object")
    tags = _clean(data.get("tags") or [])
    if not tags:
        raise EnhanceError("the model returned no tags")
    return tags, _clean(data.get("negative") or [])[:8]


async def enhance(
    client: OllamaClient,
    *,
    model: str,
    prompt: str,
    adult: bool,
    keep_alive: str = "0",
    extra_minor_characters: Iterable[str] = (),
    additions: PolicyAdditions | None = None,
) -> Enhanced:
    started = time.monotonic()
    system = SYSTEM.replace("{content_rule}", ADULT_RULE if adult else SAFE_RULE)
    try:
        raw = await client.chat(
            model,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": EXAMPLE_REQUEST},
                {"role": "assistant", "content": EXAMPLE_REPLY},
                {"role": "user", "content": prompt},
            ],
            json_format=True,
            keep_alive=keep_alive,
            options={"temperature": 0.4, "num_predict": 512},
        )
    except OllamaUnavailable:
        raise
    tags, negative = parse_reply(raw)
    positive = ", ".join(tags)
    # The policy has the last word on what the LLM wrote, exactly as on what
    # the user typed. Its negative additions are applied at generation time.
    check_prompt(
        positive,
        "",
        adult=adult,
        extra_minor_characters=extra_minor_characters,
        additions=additions,
    )
    return Enhanced(
        prompt=positive,
        negative=", ".join(negative),
        model=model,
        seconds=round(time.monotonic() - started, 1),
    )
