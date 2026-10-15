"""Graphs the generation module builds, checked against the real /object_info.

Skipped when ComfyUI is not reachable. Nothing is queued.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

from modules.engine.public import ModelTraits, WorkflowLibrary
from modules.generation.services import Hires, Sampling, build_txt2img, resolve

COMFY_URL = os.environ.get("JFAST_COMFY_URL", "http://127.0.0.1:8188")

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def object_info() -> dict[str, Any]:
    try:
        response = httpx.get(f"{COMFY_URL}/object_info", timeout=10)
    except httpx.TransportError:
        pytest.skip(f"ComfyUI not reachable at {COMFY_URL}")
    data: dict[str, Any] = response.json()
    return data


@pytest.mark.parametrize("layout", ["blend", "columns"])
@pytest.mark.parametrize("v_prediction", [False, True])
def test_multi_character_graph_matches_comfyui(
    object_info: dict[str, Any], layout: str, v_prediction: bool
) -> None:
    choice = resolve(
        "ckpt",
        "waiIllustriousSDXL_v170.safetensors",
        ModelTraits(readable=True, architecture="sdxl", v_prediction=v_prediction),
    )
    assert choice is not None
    graph = build_txt2img(
        WorkflowLibrary.from_dir(),
        choice,
        positive="2girls, cafe",
        negative="lowres",
        sampling=Sampling(1216, 832, 20, 6.0, "euler", "normal", 1, 1),
        loras=[],
        characters=["yor briar, black dress", "tifa lockhart, white tank top"],
        layout=layout,
        # Every combination also carries the hires pass, the most nodes at once.
        hires=Hires(),
    )
    problems: list[str] = []
    for nid, node in graph.items():
        spec = object_info.get(node["class_type"])
        if not isinstance(spec, dict):
            problems.append(f"#{nid}: unknown node {node['class_type']}")
            continue
        declared: set[str] = set()
        for group in ("required", "optional"):
            declared |= set((spec.get("input", {}).get(group) or {}).keys())
        unknown = set(node["inputs"]) - declared
        if unknown:
            problems.append(f"#{nid} {node['class_type']}: {sorted(unknown)}")
    assert not problems, "\n".join(problems)
