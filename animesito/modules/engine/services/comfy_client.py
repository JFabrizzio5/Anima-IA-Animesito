"""Async client for the ComfyUI HTTP and WebSocket API.

The transport and the WebSocket connector are injectable, so tests drive the
whole client against a fake ComfyUI without a GPU or a network.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from shared.enums import MediaKind

#: Output keys ComfyUI uses in /history for files a node saved.
_OUTPUT_KEYS: dict[str, MediaKind] = {
    "images": MediaKind.IMAGE,
    "gifs": MediaKind.VIDEO,
    "videos": MediaKind.VIDEO,
}
_VIDEO_SUFFIXES = (".mp4", ".webm", ".mov", ".mkv", ".gif")


class ComfyError(RuntimeError):
    """ComfyUI answered, but not with what was asked for."""


class ComfyUnavailable(ComfyError):
    """ComfyUI did not answer at all."""


class ComfyRejected(ComfyError):
    """ComfyUI refused the prompt: unknown node, missing model, bad input."""

    def __init__(self, message: str, node_errors: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.node_errors = node_errors or {}


@dataclass(frozen=True, slots=True)
class OutputFile:
    filename: str
    subfolder: str
    type: str
    media: MediaKind


@dataclass(frozen=True, slots=True)
class ComfyEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def prompt_id(self) -> str | None:
        value = self.data.get("prompt_id")
        return value if isinstance(value, str) else None


class WsConnection(Protocol):
    def __aiter__(self) -> AsyncIterator[str | bytes]: ...


WsConnect = Callable[[str], AbstractAsyncContextManager[WsConnection]]


def _default_ws_connect(url: str) -> AbstractAsyncContextManager[WsConnection]:
    from websockets.asyncio.client import connect

    # Previews arrive as binary frames of a few hundred KB; the default 1 MiB
    # cap closes the socket on a large one.
    return connect(url, max_size=16 * 1024 * 1024, open_timeout=10)


class ComfyClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        ws_connect: WsConnect | None = None,
        client_id: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id or uuid.uuid4().hex
        self._timeout = timeout
        self._transport = transport
        self._ws_connect = ws_connect or _default_ws_connect
        self._http: httpx.AsyncClient | None = None

    # -- lifecycle ---------------------------------------------------------

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
            raise RuntimeError("ComfyClient used before start()")
        return self._http

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self.http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ComfyUnavailable(f"ComfyUI is not reachable at {self.base_url}: {exc}") from exc
        if response.status_code >= 500:
            raise ComfyError(f"ComfyUI {method} {path} failed: HTTP {response.status_code}")
        return response

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ComfyError(f"ComfyUI {method} {path}: HTTP {response.status_code}")
        return response.json()

    # -- reads -------------------------------------------------------------

    async def system_stats(self) -> dict[str, Any]:
        data: dict[str, Any] = await self._json("GET", "/system_stats")
        return data

    async def object_info(self, node: str | None = None) -> dict[str, Any]:
        path = f"/object_info/{node}" if node else "/object_info"
        data: dict[str, Any] = await self._json("GET", path)
        return data

    async def choices(self, node: str, input_name: str) -> list[str]:
        """The options a COMBO input offers: model files, samplers, schedulers."""
        info = await self.object_info(node)
        spec = info.get(node, {}).get("input", {})
        for group in ("required", "optional"):
            entry = spec.get(group, {}).get(input_name)
            if entry:
                return _combo_options(entry)
        return []

    async def queue_depth(self) -> tuple[int, int]:
        data = await self._json("GET", "/queue")
        return len(data.get("queue_running", [])), len(data.get("queue_pending", []))

    async def queued_prompt_ids(self) -> set[str]:
        """Prompt ids ComfyUI is running or still holds in its queue."""
        data = await self._json("GET", "/queue")
        ids: set[str] = set()
        for entry in [*data.get("queue_running", []), *data.get("queue_pending", [])]:
            # Each entry is [number, prompt_id, prompt, extra_data, outputs].
            if isinstance(entry, list) and len(entry) > 1 and isinstance(entry[1], str):
                ids.add(entry[1])
        return ids

    async def history(self, prompt_id: str) -> dict[str, Any] | None:
        data = await self._json("GET", f"/history/{prompt_id}")
        entry = data.get(prompt_id)
        return entry if isinstance(entry, dict) else None

    async def outputs(self, prompt_id: str) -> list[OutputFile]:
        entry = await self.history(prompt_id)
        return parse_outputs(entry or {})

    async def view(self, file: OutputFile) -> bytes:
        params = {"filename": file.filename, "subfolder": file.subfolder, "type": file.type}
        response = await self._request("GET", "/view", params=params)
        if response.status_code != 200:
            raise ComfyError(
                f"ComfyUI has no output {file.filename!r} (HTTP {response.status_code})"
            )
        return response.content

    # -- writes ------------------------------------------------------------

    async def queue_prompt(self, graph: dict[str, Any]) -> str:
        response = await self._request(
            "POST", "/prompt", json={"prompt": graph, "client_id": self.client_id}
        )
        body = _safe_json(response)
        if response.status_code >= 400:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            message = error.get("message") if isinstance(error, dict) else None
            raise ComfyRejected(
                message or f"ComfyUI rejected the prompt (HTTP {response.status_code})",
                body.get("node_errors") if isinstance(body, dict) else None,
            )
        prompt_id = body.get("prompt_id") if isinstance(body, dict) else None
        if not isinstance(prompt_id, str):
            raise ComfyError("ComfyUI accepted the prompt but returned no prompt_id")
        return prompt_id

    async def upload_image(self, data: bytes, filename: str, *, overwrite: bool = True) -> str:
        """Upload into ComfyUI's input folder; returns the name LoadImage expects."""
        response = await self._request(
            "POST",
            "/upload/image",
            files={"image": (filename, data)},
            data={"overwrite": "true" if overwrite else "false", "type": "input"},
        )
        body = _safe_json(response)
        if response.status_code >= 400 or not isinstance(body, dict) or "name" not in body:
            raise ComfyError(f"ComfyUI refused the upload of {filename!r}")
        subfolder = body.get("subfolder") or ""
        return f"{subfolder}/{body['name']}" if subfolder else str(body["name"])

    async def interrupt(self, prompt_id: str | None = None) -> None:
        payload = {"prompt_id": prompt_id} if prompt_id else {}
        await self._request("POST", "/interrupt", json=payload)

    async def delete_queued(self, prompt_ids: Sequence[str]) -> None:
        await self._request("POST", "/queue", json={"delete": list(prompt_ids)})

    async def free(self, *, unload_models: bool = True, free_memory: bool = True) -> None:
        await self._request(
            "POST", "/free", json={"unload_models": unload_models, "free_memory": free_memory}
        )

    # -- events ------------------------------------------------------------

    async def events(self) -> AsyncIterator[ComfyEvent]:
        """Status/progress/execution events for this client id until the socket closes."""
        ws_base = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        url = f"{ws_base}/ws?clientId={self.client_id}"
        try:
            async with self._ws_connect(url) as connection:
                async for message in connection:
                    if isinstance(message, bytes):
                        continue
                    event = parse_event(message)
                    if event is not None:
                        yield event
        except (OSError, TimeoutError) as exc:
            raise ComfyUnavailable(f"ComfyUI WebSocket at {url} failed: {exc}") from exc


def _combo_options(entry: Any) -> list[str]:
    # Older ComfyUI: [["a", "b"], {...}]. Newer: ["COMBO", {"options": [...]}].
    if isinstance(entry, list) and entry:
        head = entry[0]
        if isinstance(head, list):
            return [str(option) for option in head]
        if head == "COMBO" and len(entry) > 1 and isinstance(entry[1], dict):
            return [str(option) for option in entry[1].get("options", [])]
    return []


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}


def parse_event(raw: str) -> ComfyEvent | None:
    try:
        message = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        return None
    data = message.get("data")
    return ComfyEvent(type=message["type"], data=data if isinstance(data, dict) else {})


def parse_outputs(entry: dict[str, Any]) -> list[OutputFile]:
    """Files the prompt saved to the output folder, in node order."""
    found: list[OutputFile] = []
    for node_output in (entry.get("outputs") or {}).values():
        if not isinstance(node_output, dict):
            continue
        for key, media in _OUTPUT_KEYS.items():
            for item in node_output.get(key) or []:
                if not isinstance(item, dict) or item.get("type") != "output":
                    continue
                filename = str(item.get("filename", ""))
                if not filename:
                    continue
                kind = MediaKind.VIDEO if filename.lower().endswith(_VIDEO_SUFFIXES) else media
                found.append(
                    OutputFile(
                        filename=filename,
                        subfolder=str(item.get("subfolder", "")),
                        type="output",
                        media=kind,
                    )
                )
    return found
