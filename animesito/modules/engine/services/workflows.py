"""ComfyUI workflows as data, patched by anchor.

Each ``workflows/*.api.json`` is a graph in ComfyUI's API format. Nodes the
code needs to touch carry an anchor in ``_meta.title`` (``@ckpt``,
``@positive``, ``@sampler``...), so a workflow can be re-exported from the
ComfyUI editor without the code depending on node ids.

The library is loaded once, at build time; ``load`` hands out deep copies.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Graph = dict[str, dict[str, Any]]
Ref = list[Any]

WORKFLOW_DIR = Path(__file__).resolve().parent.parent / "workflows"
_SUFFIX = ".api.json"


class WorkflowError(ValueError):
    """A workflow is missing, malformed, or lacks an anchor the code needs."""


@dataclass(frozen=True, slots=True)
class LoraRef:
    name: str
    strength_model: float = 1.0
    strength_clip: float = 1.0


class WorkflowLibrary:
    def __init__(self, graphs: dict[str, Graph]) -> None:
        self._graphs = graphs

    @classmethod
    def from_dir(cls, directory: Path = WORKFLOW_DIR) -> WorkflowLibrary:
        graphs: dict[str, Graph] = {}
        for path in sorted(directory.glob(f"*{_SUFFIX}")):
            name = path.name[: -len(_SUFFIX)]
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise WorkflowError(f"workflow {name!r} is not valid JSON: {exc}") from exc
            if not isinstance(data, dict) or not all(
                isinstance(node, dict) and "class_type" in node for node in data.values()
            ):
                raise WorkflowError(f"workflow {name!r} is not in ComfyUI API format")
            graphs[name] = data
        return cls(graphs)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._graphs))

    def load(self, name: str) -> Graph:
        try:
            return copy.deepcopy(self._graphs[name])
        except KeyError:
            raise WorkflowError(
                f"unknown workflow {name!r}; have {', '.join(self.names)}"
            ) from None

    def class_types(self) -> dict[str, set[str]]:
        """Every node class each workflow uses, for validation against /object_info."""
        return {
            name: {str(node["class_type"]) for node in graph.values()}
            for name, graph in self._graphs.items()
        }


# -- graph helpers -----------------------------------------------------------


def anchor_of(node: dict[str, Any]) -> str | None:
    title = node.get("_meta", {}).get("title")
    return title if isinstance(title, str) and title.startswith("@") else None


def node_id(graph: Graph, anchor: str) -> str:
    for nid, node in graph.items():
        if anchor_of(node) == anchor:
            return nid
    raise WorkflowError(f"workflow has no node anchored {anchor!r}")


def has_anchor(graph: Graph, anchor: str) -> bool:
    return any(anchor_of(node) == anchor for node in graph.values())


def set_inputs(graph: Graph, anchor: str, **inputs: Any) -> None:
    graph[node_id(graph, anchor)]["inputs"].update(inputs)


def ref(nid: str, slot: int) -> Ref:
    return [nid, slot]


def _next_id(graph: Graph) -> str:
    numeric = [int(nid) for nid in graph if nid.isdigit()]
    return str(max(numeric, default=0) + 1)


def add_node(graph: Graph, class_type: str, inputs: dict[str, Any], title: str = "") -> str:
    nid = _next_id(graph)
    graph[nid] = {"class_type": class_type, "inputs": inputs}
    if title:
        graph[nid]["_meta"] = {"title": title}
    return nid


def rewire(graph: Graph, old: Ref, new: Ref, *, skip: Iterable[str] = ()) -> int:
    """Point every input that reads ``old`` at ``new``. Returns how many moved."""
    skipped = set(skip)
    moved = 0
    for nid, node in graph.items():
        if nid in skipped:
            continue
        for key, value in node.get("inputs", {}).items():
            if isinstance(value, list) and value == old:
                node["inputs"][key] = list(new)
                moved += 1
    return moved


def insert_lora_chain(
    graph: Graph,
    loras: Sequence[LoraRef],
    *,
    model: Ref,
    clip: Ref | None,
) -> tuple[Ref, Ref | None]:
    """Chain LoRA loaders after ``model``/``clip`` and rewire their consumers.

    With ``clip=None`` (Flux, video) the model-only loader is used. Returns the
    refs the rest of the graph now reads.
    """
    current_model, current_clip = list(model), list(clip) if clip is not None else None
    inserted: list[str] = []
    for lora in loras:
        if current_clip is not None:
            nid = add_node(
                graph,
                "LoraLoader",
                {
                    "model": current_model,
                    "clip": current_clip,
                    "lora_name": lora.name,
                    "strength_model": lora.strength_model,
                    "strength_clip": lora.strength_clip,
                },
            )
            current_model, current_clip = ref(nid, 0), ref(nid, 1)
        else:
            nid = add_node(
                graph,
                "LoraLoaderModelOnly",
                {
                    "model": current_model,
                    "lora_name": lora.name,
                    "strength_model": lora.strength_model,
                },
            )
            current_model = ref(nid, 0)
        inserted.append(nid)
    if inserted:
        rewire(graph, model, current_model, skip=inserted)
        if clip is not None and current_clip is not None:
            rewire(graph, clip, current_clip, skip=inserted)
    return current_model, current_clip


def insert_v_prediction(graph: Graph, *, model: Ref, rescale: float = 0.7) -> Ref:
    """Sample a v-prediction checkpoint as one: ztSNR schedule plus CFG rescale.

    Without this a v-pred model (NoobAI v-pred) is sampled as epsilon and
    every image comes out grey and washed out.
    """
    sampling = add_node(
        graph,
        "ModelSamplingDiscrete",
        {"model": list(model), "sampling": "v_prediction", "zsnr": True},
    )
    rescaled = add_node(graph, "RescaleCFG", {"model": ref(sampling, 0), "multiplier": rescale})
    rewire(graph, model, ref(rescaled, 0), skip=(sampling, rescaled))
    return ref(rescaled, 0)
