"""Job events fan-out: whoever changes a job publishes, every SSE stream listens.

Redis pub/sub in deployment, because the dispatcher (in the worker) and the
browser's stream (in the API) are different processes. In-memory for tests.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

from ..models import JobEvent

CHANNEL = "animesito:jobs"

logger = logging.getLogger("animesito.jobs")


class ProgressBus(Protocol):
    async def publish(self, event: JobEvent) -> None: ...

    def subscribe(self) -> AsyncIterator[JobEvent]: ...


class RedisBus:
    def __init__(self, client: Any, channel: str = CHANNEL) -> None:
        self._client = client
        self._channel = channel

    async def publish(self, event: JobEvent) -> None:
        try:
            await self._client.publish(self._channel, event.model_dump_json())
        except Exception:  # a lost progress tick must never fail the job itself
            logger.warning("could not publish job event", exc_info=True)

    async def subscribe(self) -> AsyncIterator[JobEvent]:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(self._channel)
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if message is None or message.get("type") != "message":
                    continue
                try:
                    yield JobEvent.model_validate_json(message["data"])
                except ValueError:
                    continue
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(self._channel)
                await pubsub.aclose()


class MemoryBus:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[JobEvent]] = set()
        self.published: list[JobEvent] = []

    async def publish(self, event: JobEvent) -> None:
        self.published.append(event)
        for queue in list(self._queues):
            queue.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[JobEvent]:
        queue: asyncio.Queue[JobEvent] = asyncio.Queue()
        self._queues.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._queues.discard(queue)
