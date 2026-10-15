"""The dispatcher and ingest against a fake ComfyUI, in-memory SQLite and bus."""

from __future__ import annotations

import io
from typing import Any

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from jfastframework.errors import ConflictError

from modules.engine.public import ComfyEvent, ComfyUnavailable
from modules.gallery.public import get_summary
from modules.jobs.models import Job, NewJob
from modules.jobs.repositories import JobRepository
from modules.jobs.services import Dispatcher, JobService, MemoryBus, ingest_job
from shared.enums import JobKind, JobStatus
from tests.fakes import FakeComfy, MemoryDisk

GRAPH: dict[str, Any] = {
    "1": {"class_type": "LoadImage", "inputs": {"image": ""}, "_meta": {"title": "@ref"}},
    "9": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "x"},
        "_meta": {"title": "@save"},
    },
}


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 96), "purple").save(buffer, format="PNG")
    return buffer.getvalue()


class Harness:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker
        self.fake = FakeComfy()
        self.client = self.fake.client()
        self.bus = MemoryBus()
        self.disk = MemoryDisk()
        self.ingested: list[str] = []
        self.hooks_run = 0

        async def enqueue_ingest(job_id: str) -> None:
            self.ingested.append(job_id)

        async def hook() -> None:
            self.hooks_run += 1

        self.dispatcher = Dispatcher(
            sessionmaker=sessionmaker,
            comfy=self.client,
            bus=self.bus,
            enqueue_ingest=enqueue_ingest,
            disk=self.disk,
            before_submit=[hook],
        )

    async def enqueue(self, **overrides: Any) -> str:
        values: dict[str, Any] = {
            "kind": JobKind.IMAGE,
            "title": "test",
            "workflow": "sdxl_txt2img",
            "graph": GRAPH,
            "params": {"prompt": "1girl", "seed": 7, "model": "ckpt:a.safetensors"},
        }
        values.update(overrides)
        async with self.sessionmaker() as session, session.begin():
            job = await JobService(JobRepository(session)).enqueue(NewJob(**values))
            return job.id

    async def job(self, job_id: str) -> Job:
        async with self.sessionmaker() as session:
            found = await JobRepository(session).get(job_id)
            assert found is not None
            return found


@pytest.fixture
async def harness(sessionmaker: async_sessionmaker[AsyncSession]) -> Any:
    harness = Harness(sessionmaker)
    await harness.client.start()
    yield harness
    await harness.client.close()


async def test_full_lifecycle_to_the_gallery(harness: Harness) -> None:
    job_id = await harness.enqueue()
    assert await harness.dispatcher.submit_next() is True
    assert harness.hooks_run == 1
    assert harness.fake.prompts[0]["prompt"]["9"]["class_type"] == "SaveImage"
    job = await harness.job(job_id)
    assert job.status == JobStatus.SUBMITTED and job.comfy_prompt_id == "p1"

    # Only one of our prompts in ComfyUI at a time.
    await harness.enqueue()
    assert await harness.dispatcher.submit_next() is False

    await harness.dispatcher.handle(ComfyEvent("execution_start", {"prompt_id": "p1"}))
    assert (await harness.job(job_id)).status == JobStatus.RUNNING
    await harness.dispatcher.handle(
        ComfyEvent("progress", {"prompt_id": "p1", "value": 10, "max": 20})
    )
    job = await harness.job(job_id)
    assert job.progress == pytest.approx(0.475) and job.progress_text == "Paso 10/20"

    harness.fake.history["p1"] = {
        "status": {"status_str": "success", "completed": True},
        "outputs": {"9": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}},
    }
    harness.fake.files["out.png"] = png()
    await harness.dispatcher.handle(ComfyEvent("execution_success", {"prompt_id": "p1"}))
    assert (await harness.job(job_id)).status == JobStatus.INGESTING
    assert harness.ingested == [job_id]

    # A duplicate completion signal does not enqueue a second ingest.
    await harness.dispatcher.handle(ComfyEvent("executing", {"prompt_id": "p1", "node": None}))
    assert harness.ingested == [job_id]

    ids = await ingest_job(
        sessionmaker=harness.sessionmaker,
        comfy=harness.client,
        disk=harness.disk,
        bus=harness.bus,
        job_id=job_id,
    )
    job = await harness.job(job_id)
    assert job.status == JobStatus.DONE and job.result_ids == ids and len(ids) == 1
    async with harness.sessionmaker() as session:
        saved = await get_summary(session, tenant_id=None, generation_id=ids[0])
        assert saved is not None and saved.seed == 7 and saved.prompt == "1girl"
    assert harness.bus.published[-1].status == JobStatus.DONE

    # Redelivered ingest is a no-op.
    again = await ingest_job(
        sessionmaker=harness.sessionmaker,
        comfy=harness.client,
        disk=harness.disk,
        bus=harness.bus,
        job_id=job_id,
    )
    assert again == []


async def test_rejected_prompt_fails_the_job_with_node_details(harness: Harness) -> None:
    job_id = await harness.enqueue()
    harness.fake.reject_with = {
        "error": {"message": "Prompt outputs failed validation"},
        "node_errors": {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "errors": [{"message": "Value not in list", "details": "ckpt_name: x not in []"}],
            }
        },
    }
    assert await harness.dispatcher.submit_next() is True
    job = await harness.job(job_id)
    assert job.status == JobStatus.ERROR
    assert job.error is not None and "ckpt_name" in job.error


async def test_unreachable_comfy_returns_the_job_to_the_queue(harness: Harness) -> None:
    job_id = await harness.enqueue()
    harness.fake.reachable = False
    with pytest.raises(ComfyUnavailable):
        await harness.dispatcher.submit_next()
    job = await harness.job(job_id)
    assert job.status == JobStatus.QUEUED and job.comfy_prompt_id is None


async def test_inputs_are_uploaded_and_patched(harness: Harness) -> None:
    harness.disk.files["uploads/ref.png"] = png()
    await harness.enqueue(
        inputs=[{"storage_key": "uploads/ref.png", "anchor": "@ref", "field": "image"}]
    )
    await harness.dispatcher.submit_next()
    assert len(harness.fake.uploads) == 1
    assert harness.fake.prompts[0]["prompt"]["1"]["inputs"]["image"] == "ref.png"


async def test_execution_error_and_foreign_prompts(harness: Harness) -> None:
    job_id = await harness.enqueue()
    await harness.dispatcher.submit_next()
    await harness.dispatcher.handle(
        ComfyEvent("progress", {"prompt_id": "someone-else", "value": 1, "max": 2})
    )
    await harness.dispatcher.handle(
        ComfyEvent(
            "execution_error",
            {"prompt_id": "p1", "node_type": "KSampler", "exception_message": "CUDA out of memory"},
        )
    )
    job = await harness.job(job_id)
    assert job.status == JobStatus.ERROR and job.error == "KSampler: CUDA out of memory"


async def test_success_before_history_waits_for_the_final_event(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ComfyUI sends execution_success before it writes the history."""
    monkeypatch.setattr("modules.jobs.services.dispatcher.HISTORY_RETRY_SECONDS", 0)
    job_id = await harness.enqueue()
    await harness.dispatcher.submit_next()
    await harness.dispatcher.handle(ComfyEvent("execution_start", {"prompt_id": "p1"}))
    await harness.dispatcher.handle(ComfyEvent("execution_success", {"prompt_id": "p1"}))
    assert (await harness.job(job_id)).status == JobStatus.RUNNING
    assert harness.ingested == []

    harness.fake.history["p1"] = {
        "outputs": {"9": {"images": [{"filename": "late.png", "subfolder": "", "type": "output"}]}}
    }
    await harness.dispatcher.handle(ComfyEvent("executing", {"prompt_id": "p1", "node": None}))
    assert (await harness.job(job_id)).status == JobStatus.INGESTING
    assert harness.ingested == [job_id]


async def test_final_event_without_outputs_fails_after_retries(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("modules.jobs.services.dispatcher.HISTORY_RETRY_SECONDS", 0)
    job_id = await harness.enqueue()
    await harness.dispatcher.submit_next()
    await harness.dispatcher.handle(ComfyEvent("executing", {"prompt_id": "p1", "node": None}))
    job = await harness.job(job_id)
    assert job.status == JobStatus.ERROR and "sin guardar" in (job.error or "")


async def test_reconcile_settles_missed_jobs(harness: Harness) -> None:
    lost = await harness.enqueue()
    await harness.dispatcher.submit_next()  # p1, then ComfyUI "restarts"
    harness.dispatcher._inflight.clear()
    await harness.dispatcher.reconcile()
    assert (await harness.job(lost)).status == JobStatus.ERROR

    finished = await harness.enqueue()
    await harness.dispatcher.submit_next()  # p2 finished while we were away
    harness.dispatcher._inflight.clear()
    harness.fake.history["p2"] = {
        "status": {"status_str": "success"},
        "outputs": {"9": {"images": [{"filename": "o.png", "subfolder": "", "type": "output"}]}},
    }
    await harness.dispatcher.reconcile()
    assert (await harness.job(finished)).status == JobStatus.INGESTING


async def test_cancel_rules(harness: Harness) -> None:
    job_id = await harness.enqueue()
    async with harness.sessionmaker() as session, session.begin():
        cancelled = await JobService(JobRepository(session)).cancel(job_id)
        assert cancelled.status == JobStatus.CANCELLED
    async with harness.sessionmaker() as session, session.begin():
        with pytest.raises(ConflictError):
            await JobService(JobRepository(session)).cancel(job_id)
    # A cancelled job is never submitted.
    assert await harness.dispatcher.submit_next() is False
