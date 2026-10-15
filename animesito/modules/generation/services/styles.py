"""Artistic styles ported from v1's "Anime Classic" (see styles.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STYLES_FILE = Path(__file__).resolve().parent.parent / "styles.toml"


@dataclass(frozen=True, slots=True)
class Style:
    id: str
    group: str
    label: str
    pos: str
    neg: str
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    width: int | None = None
    height: int | None = None
    hires: bool = False


def _load(path: Path = STYLES_FILE) -> dict[str, Style]:
    raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    return {item["id"]: Style(**item) for item in raw.get("styles", [])}


STYLES: dict[str, Style] = _load()
