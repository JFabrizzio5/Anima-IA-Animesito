"""A fake ComfyUI for tests: an httpx MockTransport plus a scripted WebSocket.

It records every prompt queued so a test can assert on the exact graph the
app would have sent to the GPU.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx

from modules.engine.public import ComfyClient


class FakeComfy:
    def __init__(self) -> None:
        self.prompts: list[dict[str, Any]] = []
        self.uploads: list[str] = []
        self.interrupted: list[str | None] = []
        self.freed = 0
        self.history: dict[str, Any] = {}
        self.files: dict[str, bytes] = {}
        self.object_info: dict[str, Any] = {
            "CheckpointLoaderSimple": {
                "input": {
                    "required": {
                        "ckpt_name": [
                            [
                                "model_a.safetensors",
                                "noobai_vpred.safetensors",
                                "svd_xt.safetensors",
                            ]
                        ]
                    }
                }
            },
            "UnetLoaderGGUF": {
                "input": {
                    "required": {
                        "unet_name": [
                            "COMBO",
                            {
                                "options": [
                                    "flux1-dev-Q5_K_S.gguf",
                                    "Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf",
                                ]
                            },
                        ]
                    }
                }
            },
            "LoraLoader": {
                "input": {
                    "required": {
                        "lora_name": [["detail.safetensors", "flux_lustly-ai_v1.safetensors"]]
                    }
                }
            },
            "KSampler": {
                "input": {
                    "required": {
                        "sampler_name": [["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde"]],
                        "scheduler": [["normal", "karras", "simple"]],
                    }
                }
            },
        }
        self.reject_with: dict[str, Any] | None = None
        self.ws_messages: list[str | bytes] = []
        self.reachable = True

    # -- http ---------------------------------------------------------------

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.reachable:
            raise httpx.ConnectError("connection refused", request=request)
        path = request.url.path
        if path == "/prompt" and request.method == "POST":
            if self.reject_with is not None:
                return httpx.Response(400, json=self.reject_with)
            body = json.loads(request.content)
            self.prompts.append(body)
            return httpx.Response(200, json={"prompt_id": f"p{len(self.prompts)}", "number": 1})
        if path.startswith("/history/"):
            prompt_id = path.rsplit("/", 1)[-1]
            entry = self.history.get(prompt_id)
            return httpx.Response(200, json={prompt_id: entry} if entry else {})
        if path == "/view":
            name = request.url.params.get("filename", "")
            if name in self.files:
                return httpx.Response(200, content=self.files[name])
            return httpx.Response(404)
        if path == "/upload/image":
            self.uploads.append(request.headers.get("content-type", ""))
            return httpx.Response(200, json={"name": "ref.png", "subfolder": "", "type": "input"})
        if path == "/interrupt":
            body = json.loads(request.content or b"{}")
            self.interrupted.append(body.get("prompt_id"))
            return httpx.Response(200)
        if path == "/free":
            self.freed += 1
            return httpx.Response(200)
        if path == "/queue" and request.method == "GET":
            return httpx.Response(200, json={"queue_running": [], "queue_pending": []})
        if path == "/queue" and request.method == "POST":
            return httpx.Response(200)
        if path == "/system_stats":
            return httpx.Response(
                200,
                json={
                    "system": {"comfyui_version": "0.27.0"},
                    "devices": [
                        {
                            "name": "cuda:0 NVIDIA GeForce RTX 5070",
                            "vram_total": 12 * 1024**3,
                            "vram_free": 6 * 1024**3,
                        }
                    ],
                },
            )
        if path.startswith("/object_info"):
            node = path.removeprefix("/object_info").strip("/")
            if node:
                return httpx.Response(200, json={node: self.object_info.get(node, {})})
            return httpx.Response(200, json=self.object_info)
        return httpx.Response(404)

    # -- websocket ----------------------------------------------------------

    @asynccontextmanager
    async def ws_connect(self, url: str) -> AsyncIterator[_ScriptedSocket]:
        yield _ScriptedSocket(list(self.ws_messages))

    def client(self) -> ComfyClient:
        return ComfyClient(
            "http://comfy.test",
            transport=httpx.MockTransport(self.handler),
            ws_connect=self.ws_connect,
            client_id="test-client",
        )


class _ScriptedSocket:
    def __init__(self, messages: list[str | bytes]) -> None:
        self._messages = messages

    def __aiter__(self) -> AsyncIterator[str | bytes]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str | bytes]:
        for message in self._messages:
            yield message


def event(kind: str, **data: Any) -> str:
    return json.dumps({"type": kind, "data": data})


class MemoryDisk:
    """Stand-in for a jfastframework storage disk."""

    name = "public"
    visibility = "public"

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, **_: Any) -> None:
        self.files[key] = data

    async def get(self, key: str) -> bytes:
        return self.files[key]

    async def delete(self, key: str) -> bool:
        return self.files.pop(key, None) is not None

    def url(self, key: str) -> str:
        return f"/storage/public/{key}"
