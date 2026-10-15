"""The Engine module's public facade.

Other modules reach ComfyUI through these names only. No session and no
tenant: the engine holds no rows, it talks to ComfyUI and reads model files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .services import (
    ComfyClient,
    ComfyError,
    ComfyEvent,
    ComfyRejected,
    ComfyUnavailable,
    Graph,
    LoraRef,
    ModelInspector,
    ModelTraits,
    OutputFile,
    Ref,
    WorkflowError,
    WorkflowLibrary,
    add_node,
    has_anchor,
    insert_lora_chain,
    insert_v_prediction,
    node_id,
    ref,
    rewire,
    set_inputs,
)

if TYPE_CHECKING:
    from jfastframework.context import AppContext


def comfy(ctx: AppContext) -> ComfyClient:
    return ctx.require("comfy", ComfyClient)


def workflows(ctx: AppContext) -> WorkflowLibrary:
    return ctx.require("comfy.workflows", WorkflowLibrary)


def inspector(ctx: AppContext) -> ModelInspector:
    return ctx.require("comfy.inspector", ModelInspector)


__all__ = [
    "ComfyClient",
    "ComfyError",
    "ComfyEvent",
    "ComfyRejected",
    "ComfyUnavailable",
    "Graph",
    "LoraRef",
    "ModelInspector",
    "ModelTraits",
    "OutputFile",
    "Ref",
    "WorkflowError",
    "WorkflowLibrary",
    "add_node",
    "comfy",
    "has_anchor",
    "insert_lora_chain",
    "insert_v_prediction",
    "inspector",
    "node_id",
    "ref",
    "rewire",
    "set_inputs",
    "workflows",
]
