"""Every shipped workflow against the real ComfyUI's /object_info.

Skipped when ComfyUI is not reachable. Reads node definitions only; nothing is
queued and the GPU is not touched.
"""

from __future__ import annotations

import os

import httpx
import pytest

from modules.engine.services import WorkflowLibrary

COMFY_URL = os.environ.get("JFAST_COMFY_URL", "http://127.0.0.1:8188")

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def object_info() -> dict[str, object]:
    try:
        response = httpx.get(f"{COMFY_URL}/object_info", timeout=10)
    except httpx.TransportError:
        pytest.skip(f"ComfyUI not reachable at {COMFY_URL}")
    response.raise_for_status()
    data: dict[str, object] = response.json()
    return data


def test_every_node_class_exists(object_info: dict[str, object]) -> None:
    missing = {
        name: sorted(classes - object_info.keys())
        for name, classes in WorkflowLibrary.from_dir().class_types().items()
        if classes - object_info.keys()
    }
    assert not missing, f"node classes ComfyUI does not have: {missing}"


def test_every_literal_input_is_declared(object_info: dict[str, object]) -> None:
    library = WorkflowLibrary.from_dir()
    problems: list[str] = []
    for name in library.names:
        for nid, node in library.load(name).items():
            spec = object_info.get(node["class_type"])
            if not isinstance(spec, dict):
                continue
            declared: set[str] = set()
            for group in ("required", "optional"):
                declared |= set((spec.get("input", {}).get(group) or {}).keys())
            unknown = set(node["inputs"]) - declared
            if unknown:
                problems.append(f"{name}#{nid} {node['class_type']}: {sorted(unknown)}")
    assert not problems, "\n".join(problems)
