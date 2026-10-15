from __future__ import annotations

import json
import random
import struct
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from jfastframework.errors import ValidationError

from modules.engine.public import ModelInspector, WorkflowLibrary, node_id
from modules.generation.models import ImageRequest
from modules.generation.services import STYLES, GenerationService
from modules.jobs.public import recent
from tests.fakes import FakeComfy

HEADER: dict[str, Any] = {
    "conditioner.embedders.1.x": {},
    "model.diffusion_model.input_blocks.0": {},
}


@pytest.fixture
async def service(db_session: AsyncSession, tmp_path: Path) -> Any:
    (tmp_path / "checkpoints").mkdir()
    raw = json.dumps(HEADER).encode()
    (tmp_path / "checkpoints" / "model_a.safetensors").write_bytes(
        struct.pack("<Q", len(raw)) + raw
    )
    (tmp_path / "loras").mkdir()
    client = FakeComfy().client()
    await client.start()
    yield GenerationService(
        session=db_session,
        tenant_id=None,
        comfy=client,
        library=WorkflowLibrary.from_dir(),
        inspector=ModelInspector(str(tmp_path)),
        rng=random.Random(5),
    )
    await client.close()


def request(**overrides: Any) -> ImageRequest:
    values: dict[str, Any] = {"prompt": "1girl, yor briar", "model": "ckpt:model_a.safetensors"}
    values.update(overrides)
    return ImageRequest(**values)


def test_all_v1_styles_were_ported() -> None:
    assert len(STYLES) == 25  # v1: 6 clean/anime + 7 lighting + 10 themed + 2 custom
    assert STYLES["clean_anime"].pos.startswith("masterpiece, best quality, newest")
    assert STYLES["cinematic_hd"].sampler == "dpmpp_sde" and STYLES["cinematic_hd"].hires


async def test_style_replaces_quality_tags_and_negative(
    service: GenerationService, db_session: AsyncSession
) -> None:
    await service.generate_image(request(style="clean_anime"))
    graph = (await recent(db_session, tenant_id=None, limit=1))[0].graph
    positive = graph[node_id(graph, "@positive")]["inputs"]["text"]
    negative = graph[node_id(graph, "@negative")]["inputs"]["text"]
    assert positive.startswith(STYLES["clean_anime"].pos)
    assert "amazing quality" not in positive  # the family quality tags are replaced
    assert "sketch, (bad)" in negative and negative.startswith("child, loli")


async def test_hires_adds_a_second_pass(
    service: GenerationService, db_session: AsyncSession
) -> None:
    await service.generate_image(request(hires=True, steps=30))
    graph = (await recent(db_session, tenant_id=None, limit=1))[0].graph
    first, second = node_id(graph, "@sampler"), node_id(graph, "@hires_sampler")
    upscale = next(nid for nid, node in graph.items() if node["class_type"] == "LatentUpscaleBy")
    assert graph[upscale]["inputs"]["samples"] == [first, 0]
    assert graph[upscale]["inputs"]["scale_by"] == 1.5
    assert graph[second]["inputs"]["latent_image"] == [upscale, 0]
    assert graph[second]["inputs"]["denoise"] == 0.45 and graph[second]["inputs"]["steps"] == 18
    decode = next(node for node in graph.values() if node["class_type"] == "VAEDecode")
    assert decode["inputs"]["samples"] == [second, 0]


async def test_unknown_style_is_refused(service: GenerationService) -> None:
    with pytest.raises(ValidationError):
        await service.generate_image(request(style="nope"))
