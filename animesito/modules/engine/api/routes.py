"""HTTP layer for the Engine module."""

from __future__ import annotations

from fastapi import APIRouter, Request

from jfastframework.app import get_context

from ..models import EngineStatus
from ..services import ComfyClient, engine_status

router = APIRouter(prefix="/engine", tags=["engine"])


@router.get("/status", response_model=EngineStatus, summary="ComfyUI reachability and VRAM")
async def status(request: Request) -> EngineStatus:
    client = get_context(request.app).require("comfy", ComfyClient)
    return await engine_status(client)
