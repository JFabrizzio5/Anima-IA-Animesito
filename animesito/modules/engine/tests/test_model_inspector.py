from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from modules.engine.services import ModelInspector, read_traits


def write_safetensors(path: Path, header: dict[str, Any]) -> Path:
    raw = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"\x00" * 16)
    return path


async def test_v_prediction_checkpoint_is_detected(tmp_path: Path) -> None:
    folder = tmp_path / "checkpoints"
    folder.mkdir()
    write_safetensors(
        folder / "noobai.safetensors",
        {"v_pred": {"dtype": "F32", "shape": [0], "data_offsets": [0, 0]}, "ztsnr": {}},
    )
    traits = await ModelInspector(str(tmp_path)).traits("checkpoints", "noobai.safetensors")
    assert traits.readable and traits.v_prediction and traits.ztsnr


async def test_lora_base_and_triggers(tmp_path: Path) -> None:
    frequency = json.dumps({"10_oc": {"oc girl": 40, "red hair": 30, "smile": 2}})
    path = write_safetensors(
        tmp_path / "oc.safetensors",
        {
            "__metadata__": {
                "ss_base_model_version": "sdxl_base_v1-0",
                "ss_tag_frequency": frequency,
            }
        },
    )
    traits = read_traits(path)
    assert traits.base_model == "sdxl_base_v1-0"
    assert traits.trigger_words[:2] == ("oc girl", "red hair")
    assert traits.v_prediction is False


async def test_traversal_and_missing_files_get_defaults(tmp_path: Path) -> None:
    (tmp_path / "checkpoints").mkdir()
    write_safetensors(tmp_path / "secret.safetensors", {"v_pred": {}})
    inspector = ModelInspector(str(tmp_path))
    assert (await inspector.traits("checkpoints", "../secret.safetensors")).readable is False
    assert (await inspector.traits("checkpoints", "nope.safetensors")).readable is False


async def test_disabled_without_models_dir() -> None:
    inspector = ModelInspector(None)
    assert inspector.enabled is False
    assert (await inspector.traits("checkpoints", "x.safetensors")).readable is False


def test_gguf_and_garbage_are_not_parsed(tmp_path: Path) -> None:
    (tmp_path / "x.gguf").write_bytes(b"GGUF")
    (tmp_path / "bad.safetensors").write_bytes(b"\xff" * 8)
    assert read_traits(tmp_path / "x.gguf").readable is False
    assert read_traits(tmp_path / "bad.safetensors").readable is False
