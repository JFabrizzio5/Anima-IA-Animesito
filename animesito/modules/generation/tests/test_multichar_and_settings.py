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
from modules.generation.models import (
    FamilyNegativeUpdate,
    ImageRequest,
    PromptingSettingsUpdate,
)
from modules.generation.services import GenerationService, load_config, update, view
from modules.jobs.public import JobDetail, recent
from tests.fakes import FakeComfy

SDXL_HEADER: dict[str, Any] = {
    "conditioner.embedders.1.model.x": {},
    "model.diffusion_model.input_blocks.0": {},
}


@pytest.fixture
def models_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "checkpoints"
    folder.mkdir()
    raw = json.dumps(SDXL_HEADER).encode()
    (folder / "model_a.safetensors").write_bytes(struct.pack("<Q", len(raw)) + raw)
    (tmp_path / "loras").mkdir()
    return tmp_path


async def make_service(session: AsyncSession, models_dir: Path) -> tuple[GenerationService, Any]:
    client = FakeComfy().client()
    await client.start()
    service = GenerationService(
        session=session,
        tenant_id=None,
        comfy=client,
        library=WorkflowLibrary.from_dir(),
        inspector=ModelInspector(str(models_dir)),
        rng=random.Random(3),
        config=await load_config(session),
    )
    return service, client


async def latest(session: AsyncSession) -> JobDetail:
    return (await recent(session, tenant_id=None, limit=1))[0]


def request(**overrides: Any) -> ImageRequest:
    values: dict[str, Any] = {
        "prompt": "2girls, cafe, sunlight",
        "model": "ckpt:model_a.safetensors",
        "character_prompts": [
            "yor briar, spy x family, black hair, red eyes, black dress",
            "tifa lockhart, final fantasy vii, black hair, white tank top",
        ],
    }
    values.update(overrides)
    return ImageRequest(**values)


def classes(graph: dict[str, Any]) -> list[str]:
    return [node["class_type"] for node in graph.values()]


async def test_blend_encodes_each_character_apart(
    db_session: AsyncSession, models_dir: Path
) -> None:
    service, client = await make_service(db_session, models_dir)
    await service.generate_image(request())
    await client.close()
    job = await latest(db_session)
    graph = job.graph
    assert classes(graph).count("CLIPTextEncode") == 4  # scene, negative, 2 characters
    assert classes(graph).count("ConditioningConcat") == 2
    sampler = graph[node_id(graph, "@sampler")]["inputs"]
    last = graph[sampler["positive"][0]]
    assert last["class_type"] == "ConditioningConcat"
    scene = graph[node_id(graph, "@positive")]["inputs"]["text"]
    assert scene.endswith("2girls, cafe, sunlight") and "yor briar" not in scene
    assert job.params["character_prompts"][0].startswith("yor briar")
    # What is stored as "the prompt" covers everyone, for search and reuse.
    assert "tifa lockhart" in job.params["prompt"]


async def test_columns_pin_characters_left_to_right(
    db_session: AsyncSession, models_dir: Path
) -> None:
    service, client = await make_service(db_session, models_dir)
    await service.generate_image(request(layout="columns", width=1216, height=832))
    await client.close()
    graph = (await latest(db_session)).graph
    areas = sorted(
        (node["inputs"] for node in graph.values() if node["class_type"] == "ConditioningSetArea"),
        key=lambda inputs: inputs["x"],
    )
    assert [(area["x"], area["width"], area["height"]) for area in areas] == [
        (0, 608, 832),
        (608, 608, 832),
    ]
    assert classes(graph).count("ConditioningCombine") == 2


async def test_character_prompts_go_through_the_policy(
    db_session: AsyncSession, models_dir: Path
) -> None:
    service, client = await make_service(db_session, models_dir)
    with pytest.raises(ValidationError):
        await service.generate_image(
            request(adult=True, character_prompts=["yor briar", "uraraka ochako, nude"])
        )
    with pytest.raises(ValidationError):
        await service.generate_image(request(character_prompts=["   "]))
    await client.close()


async def test_settings_edit_negatives_and_add_policy(
    db_session: AsyncSession, models_dir: Path
) -> None:
    await update(
        db_session,
        PromptingSettingsUpdate(
            global_negative="text, watermark",
            family_negatives={"anime_sdxl": FamilyNegativeUpdate(negative="custom bad, blurry")},
            extra_terms=["Petite_Body", "loli", "  "],
            extra_characters=["Some Kid Character", "kitagawa marin"],
            extra_negative="flat chest",
        ),
    )
    shown = await view(db_session, learned_characters={"obscure hero"})
    # Entries already in the base list are not stored twice.
    assert shown.policy.extra_terms == ["petite body"]
    assert shown.policy.extra_characters == ["some kid character"]
    assert "loli" in shown.policy.base_terms and shown.policy.learned_characters == ["obscure hero"]
    family = next(item for item in shown.families if item.family == "anime_sdxl")
    assert family.negative == "custom bad, blurry" and family.default_negative

    service, client = await make_service(db_session, models_dir)
    await service.generate_image(request(character_prompts=[], prompt="1girl, cafe"))
    graph = (await latest(db_session)).graph
    negative = graph[node_id(graph, "@negative")]["inputs"]["text"]
    assert "custom bad, blurry" in negative and "text, watermark" in negative
    assert "flat chest" in negative
    with pytest.raises(ValidationError):
        await service.generate_image(
            request(character_prompts=[], prompt="1girl, petite body", adult=True)
        )
    with pytest.raises(ValidationError):
        await service.generate_image(
            request(character_prompts=[], prompt="some kid character", adult=True)
        )
    await client.close()


async def test_settings_reject_unknown_family_and_reset_on_empty(db_session: AsyncSession) -> None:
    with pytest.raises(ValidationError):
        await update(
            db_session, PromptingSettingsUpdate(family_negatives={"nope": FamilyNegativeUpdate()})
        )
    await update(
        db_session,
        PromptingSettingsUpdate(family_negatives={"pony": FamilyNegativeUpdate(negative="  ")}),
    )
    config = await load_config(db_session)
    assert config.negative_for("pony") is None
