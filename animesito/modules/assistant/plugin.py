"""The ``assistant`` plugin: the Ollama client, and its VRAM hand-off to ComfyUI.

It also publishes ``jobs.before_submit``: the dispatcher calls those hooks
before handing ComfyUI a prompt, and this one evicts any loaded LLM so the
render gets the whole card.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from jfastframework.plugins.base import HealthReport, Plugin, PluginMeta, PluginSettings

from .services import AssistantConfig, OllamaClient, OllamaUnavailable

if TYPE_CHECKING:
    from jfastframework.context import AppContext


class AssistantSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="JFAST_ASSISTANT_", env_file=".env", extra="ignore"
    )

    url: str = "http://127.0.0.1:11434"
    # Compared on this machine (2026-10-09): best tags of the installed models,
    # ~11 s, and at 3.8 GB the smallest -- it fits next to a resident SDXL.
    default_model: str = "dolphin-mistral:latest"
    timeout: float = 180.0
    # "0" unloads right after answering, so ComfyUI keeps its VRAM.
    keep_alive: str = "0"
    # Models above this size do not fit a 12 GB card next to anything else.
    max_model_gb: float = 10.0


class AssistantPlugin(Plugin):
    meta = PluginMeta(
        name="assistant",
        version="0.1.0",
        description="Ollama prompt enhancement and LLM/ComfyUI VRAM hand-off.",
        provides=("ollama", "assistant.config", "jobs.before_submit"),
        health_critical=False,
    )
    Settings = AssistantSettings

    def register(self, ctx: AppContext) -> None:
        settings: AssistantSettings = self.settings
        self.client = OllamaClient(settings.url, timeout=settings.timeout)
        ctx.provide("ollama", self.client)
        ctx.provide(
            "assistant.config",
            AssistantConfig(
                default_model=settings.default_model,
                keep_alive=settings.keep_alive,
                max_model_gb=settings.max_model_gb,
            ),
        )

        async def free_vram_for_comfy() -> None:
            try:
                await self.client.unload_all()
            except OllamaUnavailable:
                return

        ctx.provide("jobs.before_submit", [free_vram_for_comfy])

    async def startup(self, ctx: AppContext) -> None:
        await self.client.start()

    async def shutdown(self, ctx: AppContext) -> None:
        await self.client.close()

    async def health(self, ctx: AppContext) -> HealthReport:
        try:
            models = await self.client.models()
        except OllamaUnavailable as exc:
            return HealthReport.fail(str(exc), critical=False)
        return HealthReport.ok(f"Ollama with {len(models)} models")
