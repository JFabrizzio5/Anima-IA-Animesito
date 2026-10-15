"""Engine status: is ComfyUI up, how much VRAM is free, how deep is its queue."""

from __future__ import annotations

from ..models import EngineStatus
from .comfy_client import ComfyClient, ComfyError


async def engine_status(client: ComfyClient) -> EngineStatus:
    try:
        stats = await client.system_stats()
        running, pending = await client.queue_depth()
    except ComfyError as exc:
        return EngineStatus(reachable=False, url=client.base_url, detail=str(exc))
    devices = stats.get("devices") or [{}]
    device = devices[0] if isinstance(devices[0], dict) else {}
    mib = 1024 * 1024
    return EngineStatus(
        reachable=True,
        url=client.base_url,
        version=stats.get("system", {}).get("comfyui_version"),
        device=device.get("name"),
        vram_total_mb=int(device["vram_total"]) // mib if "vram_total" in device else None,
        vram_free_mb=int(device["vram_free"]) // mib if "vram_free" in device else None,
        running=running,
        pending=pending,
    )
