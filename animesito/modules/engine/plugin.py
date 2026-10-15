"""The ``comfy`` plugin: one ComfyUI client per process.

Registered in jfast.toml under ``[plugins.paths]`` so the API and ``jfast
worker`` build it the same way. ComfyUI being down is not fatal -- the app
still serves the gallery -- so the health report is non-critical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from jfastframework.plugins.base import HealthReport, Plugin, PluginMeta, PluginSettings

from .services.comfy_client import ComfyClient, ComfyError
from .services.model_inspector import ModelInspector
from .services.workflows import WorkflowLibrary

if TYPE_CHECKING:
    from jfastframework.context import AppContext


class ComfySettings(PluginSettings):
    model_config = SettingsConfigDict(env_prefix="JFAST_COMFY_", env_file=".env", extra="ignore")

    # ComfyUI runs natively on Windows; with WSL in mirrored networking its
    # 127.0.0.1 is this process's 127.0.0.1 too.
    url: str = "http://127.0.0.1:8188"
    timeout: float = 30.0
    # ComfyUI's models folder as this process sees it, for reading safetensors
    # headers (v-prediction, LoRA base). Optional.
    models_dir: str | None = None


class ComfyPlugin(Plugin):
    meta = PluginMeta(
        name="comfy",
        version="0.1.0",
        description="ComfyUI client, workflow library and model inspector.",
        provides=("comfy", "comfy.workflows", "comfy.inspector"),
        health_critical=False,
    )
    Settings = ComfySettings

    def register(self, ctx: AppContext) -> None:
        settings: ComfySettings = self.settings
        self.client = ComfyClient(settings.url, timeout=settings.timeout)
        ctx.provide("comfy", self.client)
        ctx.provide("comfy.workflows", WorkflowLibrary.from_dir())
        ctx.provide("comfy.inspector", ModelInspector(settings.models_dir))

    async def startup(self, ctx: AppContext) -> None:
        await self.client.start()

    async def shutdown(self, ctx: AppContext) -> None:
        await self.client.close()

    async def health(self, ctx: AppContext) -> HealthReport:
        try:
            stats = await self.client.system_stats()
        except ComfyError as exc:
            return HealthReport.fail(str(exc), critical=False)
        version = stats.get("system", {}).get("comfyui_version", "unknown")
        return HealthReport.ok(f"ComfyUI {version}")
