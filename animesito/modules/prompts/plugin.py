"""The ``prompts`` plugin: one HTTP client for Danbooru and AniList per process."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from jfastframework.plugins.base import Plugin, PluginMeta, PluginSettings

from .services import Sources

if TYPE_CHECKING:
    from jfastframework.context import AppContext


class PromptsSettings(PluginSettings):
    model_config = SettingsConfigDict(env_prefix="JFAST_PROMPTS_", env_file=".env", extra="ignore")

    danbooru_url: str = "https://danbooru.donmai.us"
    anilist_url: str = "https://graphql.anilist.co"
    timeout: float = 10.0


class PromptsPlugin(Plugin):
    meta = PluginMeta(
        name="prompts",
        version="0.1.0",
        description="Danbooru tags and AniList characters for the prompt builder.",
        requires=("cache",),
        provides=("prompts.sources",),
        health_critical=False,
    )
    Settings = PromptsSettings

    def register(self, ctx: AppContext) -> None:
        settings: PromptsSettings = self.settings
        self.sources = Sources(
            danbooru_url=settings.danbooru_url,
            anilist_url=settings.anilist_url,
            timeout=settings.timeout,
        )
        ctx.provide("prompts.sources", self.sources)

    async def startup(self, ctx: AppContext) -> None:
        await self.sources.start()

    async def shutdown(self, ctx: AppContext) -> None:
        await self.sources.close()
