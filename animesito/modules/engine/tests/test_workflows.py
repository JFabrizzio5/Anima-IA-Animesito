from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.engine.services import (
    LoraRef,
    WorkflowError,
    WorkflowLibrary,
    insert_lora_chain,
    insert_v_prediction,
    node_id,
    ref,
    set_inputs,
)


@pytest.fixture(scope="module")
def library() -> WorkflowLibrary:
    return WorkflowLibrary.from_dir()


def test_library_loads_the_shipped_workflows(library: WorkflowLibrary) -> None:
    assert {"sdxl_txt2img", "flux_txt2img"} <= set(library.names)


@pytest.mark.parametrize(
    ("name", "anchors"),
    [
        ("sdxl_txt2img", ["@ckpt", "@positive", "@negative", "@latent", "@sampler", "@save"]),
        ("flux_txt2img", ["@unet", "@positive", "@latent", "@noise", "@scheduler", "@save"]),
    ],
)
def test_every_patched_node_is_anchored(
    library: WorkflowLibrary, name: str, anchors: list[str]
) -> None:
    graph = library.load(name)
    for anchor in anchors:
        node_id(graph, anchor)


def test_load_returns_independent_copies(library: WorkflowLibrary) -> None:
    first = library.load("sdxl_txt2img")
    set_inputs(first, "@positive", text="changed")
    second = library.load("sdxl_txt2img")
    assert second[node_id(second, "@positive")]["inputs"]["text"] == ""


def test_unknown_anchor_and_workflow_raise(library: WorkflowLibrary) -> None:
    with pytest.raises(WorkflowError):
        node_id(library.load("sdxl_txt2img"), "@nope")
    with pytest.raises(WorkflowError):
        library.load("missing")


def test_lora_chain_rewires_model_and_clip_consumers(library: WorkflowLibrary) -> None:
    graph = library.load("sdxl_txt2img")
    ckpt = node_id(graph, "@ckpt")
    model, clip = insert_lora_chain(
        graph,
        [LoraRef("a.safetensors", 0.8, 0.8), LoraRef("b.safetensors", 0.5, 0.5)],
        model=ref(ckpt, 0),
        clip=ref(ckpt, 1),
    )
    sampler = graph[node_id(graph, "@sampler")]
    assert sampler["inputs"]["model"] == model
    assert graph[node_id(graph, "@positive")]["inputs"]["clip"] == clip
    assert graph[node_id(graph, "@negative")]["inputs"]["clip"] == clip
    loras = [node for node in graph.values() if node["class_type"] == "LoraLoader"]
    assert [node["inputs"]["lora_name"] for node in loras] == ["a.safetensors", "b.safetensors"]
    assert loras[0]["inputs"]["model"] == ref(ckpt, 0)
    # The VAE still comes straight from the checkpoint.
    decode = next(node for node in graph.values() if node["class_type"] == "VAEDecode")
    assert decode["inputs"]["vae"] == ref(ckpt, 2)


def test_model_only_chain_for_flux(library: WorkflowLibrary) -> None:
    graph = library.load("flux_txt2img")
    unet = node_id(graph, "@unet")
    model, clip = insert_lora_chain(
        graph, [LoraRef("f.safetensors", 0.9)], model=ref(unet, 0), clip=None
    )
    assert clip is None
    assert graph[node_id(graph, "@model_sampling")]["inputs"]["model"] == model
    assert any(node["class_type"] == "LoraLoaderModelOnly" for node in graph.values())


def test_no_loras_changes_nothing(library: WorkflowLibrary) -> None:
    graph = library.load("sdxl_txt2img")
    before = json.dumps(graph, sort_keys=True)
    ckpt = node_id(graph, "@ckpt")
    insert_lora_chain(graph, [], model=ref(ckpt, 0), clip=ref(ckpt, 1))
    assert json.dumps(graph, sort_keys=True) == before


def test_v_prediction_wraps_the_sampler_model(library: WorkflowLibrary) -> None:
    graph = library.load("sdxl_txt2img")
    ckpt = node_id(graph, "@ckpt")
    final = insert_v_prediction(graph, model=ref(ckpt, 0))
    assert graph[node_id(graph, "@sampler")]["inputs"]["model"] == final
    sampling = next(n for n in graph.values() if n["class_type"] == "ModelSamplingDiscrete")
    assert sampling["inputs"] == {"model": ref(ckpt, 0), "sampling": "v_prediction", "zsnr": True}


def test_malformed_workflow_is_refused(tmp_path: Path) -> None:
    (tmp_path / "bad.api.json").write_text('{"1": {"inputs": {}}}', encoding="utf-8")
    with pytest.raises(WorkflowError):
        WorkflowLibrary.from_dir(tmp_path)
