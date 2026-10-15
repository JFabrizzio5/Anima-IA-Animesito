"""Ollama's native API: model list, chat, and unloading models from VRAM.

Native rather than the OpenAI-compatible endpoint because ``keep_alive`` is
what lets a 12 GB card run the LLM and ComfyUI one after the other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

REASONING_MODEL = re.compile(r"deepseek-r1|qwen3|gpt-oss|magistral", re.I)


class OllamaUnavailable(RuntimeError):
    """Ollama did not answer, or answered with an error."""


@dataclass(frozen=True, slots=True)
class AssistantConfig:
    default_model: str
    keep_alive: str
    max_model_gb: float


@dataclass(frozen=True, slots=True)
class LlmModel:
    name: str
    size_bytes: int
    parameter_size: str | None
    capabilities: tuple[str, ...]

    @property
    def size_gb(self) -> float:
        return round(self.size_bytes / 1024**3, 1)

    @property
    def is_reasoning(self) -> bool:
        # Measured: deepseek-r1:14b returned empty JSON after 119 s, think off.
        return bool(REASONING_MODEL.search(self.name))

    @property
    def is_embedding(self) -> bool:
        return "embedding" in self.capabilities and "completion" not in self.capabilities


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 180.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport
        self._http: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url, timeout=self._timeout, transport=self._transport
            )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError("OllamaClient used before start()")
        return self._http

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self.http.post(path, json=payload)
        except httpx.TransportError as exc:
            raise OllamaUnavailable(f"Ollama is not reachable at {self.base_url}: {exc}") from exc
        if response.status_code >= 400:
            raise OllamaUnavailable(
                f"Ollama {path}: HTTP {response.status_code} {response.text[:200]}"
            )
        return response.json()

    async def models(self) -> list[LlmModel]:
        try:
            response = await self.http.get("/api/tags")
        except httpx.TransportError as exc:
            raise OllamaUnavailable(f"Ollama is not reachable at {self.base_url}: {exc}") from exc
        found: list[LlmModel] = []
        for item in (response.json() or {}).get("models", []):
            details = item.get("details") or {}
            found.append(
                LlmModel(
                    name=str(item.get("name")),
                    size_bytes=int(item.get("size") or 0),
                    parameter_size=details.get("parameter_size"),
                    capabilities=tuple(item.get("capabilities") or ()),
                )
            )
        return found

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_format: bool = False,
        keep_alive: str = "0",
        options: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
            "options": options or {},
        }
        if json_format:
            payload["format"] = "json"
        if REASONING_MODEL.search(model):
            # A thinking model spends its token budget on <think> and then
            # breaks the JSON; tag conversion needs no reasoning trace.
            payload["think"] = False
        data = await self._post("/api/chat", payload)
        content = (data.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise OllamaUnavailable("Ollama returned no message content")
        return content

    async def unload_all(self) -> list[str]:
        """Evict every loaded model from VRAM; returns their names."""
        try:
            response = await self.http.get("/api/ps")
        except httpx.TransportError:
            return []
        names = [str(item.get("name")) for item in (response.json() or {}).get("models", [])]
        for name in names:
            await self._post("/api/generate", {"model": name, "keep_alive": 0})
        return names
