"""What a model file says about itself, read from its safetensors header.

The header is a JSON blob at the start of the file, so this reads a few KB --
never the weights. Results are cached by (path, size, mtime).

It needs ComfyUI's ``models`` directory to be readable from this process
(``[plugin.comfy] models_dir``). Without it every model gets default traits and
generation falls back to what the filename says.
"""

from __future__ import annotations

import asyncio
import json
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: A safetensors header larger than this is not a header.
_MAX_HEADER = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ModelTraits:
    v_prediction: bool = False
    ztsnr: bool = False
    base_model: str | None = None
    trigger_words: tuple[str, ...] = field(default_factory=tuple)
    # "sdxl", "flux", "sd15" or None when the tensor names do not say.
    architecture: str | None = None
    readable: bool = False


def _architecture(keys: list[str]) -> str | None:
    if any("double_blocks." in key for key in keys):
        return "flux"
    if any(key.startswith("conditioner.embedders.1") for key in keys):
        return "sdxl"
    if any(key.startswith("cond_stage_model.transformer") for key in keys):
        return "sd15"
    if any(key.startswith("model.diffusion_model.input_blocks") for key in keys):
        return "sdxl" if any("label_emb" in key for key in keys) else "sd15"
    return None


def read_traits(path: Path) -> ModelTraits:
    """Blocking: parse the header of one ``.safetensors`` file."""
    if path.suffix.lower() != ".safetensors" or not path.is_file():
        return ModelTraits()
    with path.open("rb") as handle:
        prefix = handle.read(8)
        if len(prefix) != 8:
            return ModelTraits()
        (length,) = struct.unpack("<Q", prefix)
        if length <= 0 or length > _MAX_HEADER:
            return ModelTraits()
        try:
            header: dict[str, Any] = json.loads(handle.read(length))
        except ValueError:
            return ModelTraits()
    meta = header.get("__metadata__") or {}
    return ModelTraits(
        v_prediction="v_pred" in header or meta.get("modelspec.prediction_type") == "v",
        ztsnr="ztsnr" in header,
        base_model=_base_model(meta),
        trigger_words=_trigger_words(meta),
        architecture=_architecture([key for key in header if key != "__metadata__"]),
        readable=True,
    )


def _base_model(meta: dict[str, Any]) -> str | None:
    for key in ("ss_base_model_version", "modelspec.architecture"):
        value = meta.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _trigger_words(meta: dict[str, Any], limit: int = 8) -> tuple[str, ...]:
    """Most frequent caption tags of a kohya-trained LoRA, a usable trigger hint."""
    raw = meta.get("ss_tag_frequency")
    if not isinstance(raw, str):
        return ()
    try:
        folders = json.loads(raw)
    except ValueError:
        return ()
    counts: Counter[str] = Counter()
    if isinstance(folders, dict):
        for tags in folders.values():
            if isinstance(tags, dict):
                for tag, count in tags.items():
                    if isinstance(count, int):
                        counts[tag.strip()] += count
    return tuple(tag for tag, _ in counts.most_common(limit) if tag)


class ModelInspector:
    def __init__(self, models_dir: str | None) -> None:
        self.root = Path(models_dir) if models_dir else None
        self._cache: dict[tuple[str, int, float], ModelTraits] = {}

    @property
    def enabled(self) -> bool:
        return self.root is not None

    def _resolve(self, folder: str, filename: str) -> Path | None:
        if self.root is None:
            return None
        base = (self.root / folder).resolve()
        candidate = (base / filename).resolve()
        # A filename comes from ComfyUI's object_info, but it is still a string
        # a client can send back: never let it walk out of the models folder.
        if not candidate.is_relative_to(base):
            return None
        return candidate

    def _traits_blocking(self, folder: str, filename: str) -> ModelTraits:
        path = self._resolve(folder, filename)
        if path is None or not path.is_file():
            return ModelTraits()
        stat = path.stat()
        key = (str(path), stat.st_size, stat.st_mtime)
        cached = self._cache.get(key)
        if cached is None:
            cached = read_traits(path)
            self._cache[key] = cached
        return cached

    async def traits(self, folder: str, filename: str) -> ModelTraits:
        if self.root is None:
            return ModelTraits()
        return await asyncio.to_thread(self._traits_blocking, folder, filename)
