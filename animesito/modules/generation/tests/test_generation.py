from __future__ import annotations

import json
import random
import struct
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from jfastframework.errors import ValidationError

from modules.engine.public import ModelInspector, ModelTraits, WorkflowLibrary, node_id
from modules.generation.models import ImageRequest, LoraSpec
from modules.generation.services import (
    PROFILES,
    GenerationService,
    compose,
    detect_family,
)
from modules.jobs.public import JobDetail, recent
from modules.policy.public import minor_negative
from tests.fakes import FakeComfy

SDXL_HEADER: dict[str, Any] = {
    "conditioner.embedders.1.model.x": {},
    "model.diffusion_model.input_blocks.0": {},
}


def write_header(path: Path, header: dict[str, Any]) -> None:
    raw = json.dumps(header).encode()
    path.write_bytes(struct.pack("<Q", len(raw)) + raw)


@pytest.fixture
def models_dir(tmp_path: Path) -> Path:
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    write_header(checkpoints / "model_a.safetensors", SDXL_HEADER)
    write_header(
        checkpoints / "noobai_vpred.safetensors", {**SDXL_HEADER, "v_pred": {}, "ztsnr": {}}
    )
    write_header(checkpoints / "svd_xt.safetensors", SDXL_HEADER)
    (tmp_path / "loras").mkdir()
    return tmp_path


@pytest.fixture
async def service(db_session: AsyncSession, models_dir: Path) -> Any:
    fake = FakeComfy()
    client = fake.client()
    await client.start()
    yield GenerationService(
        session=db_session,
        tenant_id=None,
        comfy=client,
        library=WorkflowLibrary.from_dir(),
        inspector=ModelInspector(str(models_dir)),
        rng=random.Random(1),
    )
    await client.close()


def request(**overrides: Any) -> ImageRequest:
    values: dict[str, Any] = {
        "prompt": "1girl, silver hair, rooftop at night",
        "model": "ckpt:model_a.safetensors",
    }
    values.update(overrides)
    return ImageRequest(**values)


MINOR_NEGATIVE = minor_negative()


async def jobs(session: AsyncSession) -> list[JobDetail]:
    return list(reversed(await recent(session, tenant_id=None)))


@pytest.mark.parametrize(
    ("loader", "filename", "family"),
    [
        ("ckpt", "waiIllustriousSDXL_v170.safetensors", "illustrious"),
        ("ckpt", "noobaiXLNAIXL_vEPSILON.safetensors", "noobai"),
        ("ckpt", "ponyDiffusionV6XL_v6StartWithThisOne.safetensors", "pony"),
        ("ckpt", "waiREALCN_v20.safetensors", "pony_real"),
        ("ckpt", "animagine-xl-3.1.safetensors", "animagine"),
        ("ckpt", "RealVisXL_V4.0.safetensors", "realistic"),
        ("ckpt", "Juggernaut-XL_v9.safetensors", "realistic"),
        ("ckpt", "svd_xt.safetensors", None),
        ("ckpt", "redcraft22_native.safetensors", None),
        ("gguf", "flux1-dev-Q8_0.gguf", "flux"),
        ("gguf", "flux1-kontext-dev-Q5_K_M.gguf", None),
        ("gguf", "Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf", None),
    ],
)
def test_family_detection(loader: str, filename: str, family: str | None) -> None:
    assert detect_family(loader, filename, ModelTraits()) == family


def test_unknown_architecture_is_not_driven() -> None:
    traits = ModelTraits(readable=True, architecture=None)
    assert detect_family("ckpt", "mystery.safetensors", traits) is None
    assert (
        detect_family(
            "ckpt", "flux_aio.safetensors", ModelTraits(readable=True, architecture="flux")
        )
        is None
    )


def test_compose_orders_quality_rating_subject() -> None:
    pony = PROFILES["pony"]
    safe = compose(pony, prompt="1girl, smile", negative="blurry", adult=False, quality_tags=True)
    assert (
        safe.positive == "score_9, score_8_up, score_7_up, source_anime, rating_safe, 1girl, smile"
    )
    assert safe.negative.startswith(MINOR_NEGATIVE)
    assert "rating_explicit" in safe.negative and safe.negative.endswith("blurry")
    adult = compose(pony, prompt="1girl", negative="", adult=True, quality_tags=False)
    assert adult.positive == "adult, mature, rating_explicit, 1girl"
    assert "rating_explicit" not in adult.negative


async def test_options_list_families_and_skip_non_txt2img(service: GenerationService) -> None:
    options = await service.options()
    ids = {model.id: model for model in options.models}
    assert set(ids) == {
        "ckpt:model_a.safetensors",
        "ckpt:noobai_vpred.safetensors",
        "gguf:flux1-dev-Q5_K_S.gguf",
    }
    assert ids["ckpt:noobai_vpred.safetensors"].v_prediction is True
    assert ids["gguf:flux1-dev-Q5_K_S.gguf"].supports_negative is False
    assert options.engine_reachable and "euler" in options.samplers


async def test_batches_split_into_jobs_with_consecutive_seeds(
    service: GenerationService, db_session: AsyncSession
) -> None:
    response = await service.generate_image(request(count=5, batch_size=2, seed=100))
    assert len(response.jobs) == 3
    queued = await jobs(db_session)
    seeds = [job.params["seed"] for job in queued]
    batches = [job.params["batch_size"] for job in queued]
    assert seeds == [100, 102, 104] and batches == [2, 2, 1]
    graph = queued[0].graph
    assert graph[node_id(graph, "@ckpt")]["inputs"]["ckpt_name"] == "model_a.safetensors"
    assert graph[node_id(graph, "@latent")]["inputs"]["batch_size"] == 2
    positive = graph[node_id(graph, "@positive")]["inputs"]["text"]
    assert positive.startswith("masterpiece, best quality") and positive.endswith(
        "rooftop at night"
    )
    negative = graph[node_id(graph, "@negative")]["inputs"]["text"]
    assert negative.startswith(MINOR_NEGATIVE)


async def test_v_prediction_model_gets_sampling_nodes(
    service: GenerationService, db_session: AsyncSession
) -> None:
    await service.generate_image(request(model="ckpt:noobai_vpred.safetensors"))
    graph = (await jobs(db_session))[0].graph
    classes = [node["class_type"] for node in graph.values()]
    assert "ModelSamplingDiscrete" in classes and "RescaleCFG" in classes
    sampler = graph[node_id(graph, "@sampler")]["inputs"]
    assert sampler["cfg"] == PROFILES["noobai"].cfg and sampler["sampler_name"] == "euler"


async def test_flux_adult_adds_the_adult_lora(
    service: GenerationService, db_session: AsyncSession
) -> None:
    await service.generate_image(
        request(model="gguf:flux1-dev-Q5_K_S.gguf", adult=True, prompt="1woman, beach")
    )
    job = (await jobs(db_session))[0]
    loras = [node for node in job.graph.values() if node["class_type"] == "LoraLoaderModelOnly"]
    assert [node["inputs"]["lora_name"] for node in loras] == ["flux_lustly-ai_v1.safetensors"]
    assert job.params["negative"] == ""
    assert job.graph[node_id(job.graph, "@guidance")]["inputs"]["guidance"] == 3.5


async def test_policy_refusal_queues_nothing(
    service: GenerationService, db_session: AsyncSession
) -> None:
    with pytest.raises(ValidationError):
        await service.generate_image(request(prompt="1girl, uraraka ochako, nude", adult=True))
    assert await jobs(db_session) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"model": "ckpt:not_installed.safetensors"},
        {"model": "ckpt:svd_xt.safetensors"},
        {"loras": [LoraSpec(name="missing.safetensors")]},
        {"width": 833},
        {"sampler": "made_up"},
        {"width": 2048, "height": 2048},
    ],
)
async def test_invalid_requests_are_refused(
    service: GenerationService, overrides: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        await service.generate_image(request(**overrides))
