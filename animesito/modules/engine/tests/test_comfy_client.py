from __future__ import annotations

import pytest

from modules.engine.services import (
    ComfyRejected,
    ComfyUnavailable,
    OutputFile,
    engine_status,
    parse_outputs,
)
from shared.enums import MediaKind
from tests.fakes import FakeComfy, event


async def test_queue_prompt_sends_graph_and_client_id() -> None:
    fake = FakeComfy()
    client = fake.client()
    await client.start()
    prompt_id = await client.queue_prompt({"1": {"class_type": "X", "inputs": {}}})
    await client.close()
    assert prompt_id == "p1"
    assert fake.prompts[0]["client_id"] == "test-client"
    assert fake.prompts[0]["prompt"]["1"]["class_type"] == "X"


async def test_rejected_prompt_carries_node_errors() -> None:
    fake = FakeComfy()
    fake.reject_with = {
        "error": {"message": "Prompt outputs failed validation"},
        "node_errors": {"1": {"errors": [{"message": "Value not in list"}]}},
    }
    client = fake.client()
    await client.start()
    with pytest.raises(ComfyRejected) as caught:
        await client.queue_prompt({})
    await client.close()
    assert "failed validation" in str(caught.value)
    assert "1" in caught.value.node_errors


async def test_unreachable_comfy_is_a_typed_error() -> None:
    fake = FakeComfy()
    fake.reachable = False
    client = fake.client()
    await client.start()
    with pytest.raises(ComfyUnavailable):
        await client.system_stats()
    status = await engine_status(client)
    await client.close()
    assert status.reachable is False


async def test_choices_reads_both_combo_formats() -> None:
    client = FakeComfy().client()
    await client.start()
    assert await client.choices("CheckpointLoaderSimple", "ckpt_name") == [
        "model_a.safetensors",
        "noobai_vpred.safetensors",
        "svd_xt.safetensors",
    ]
    assert (await client.choices("UnetLoaderGGUF", "unet_name"))[0] == "flux1-dev-Q5_K_S.gguf"
    assert await client.choices("Missing", "x") == []
    await client.close()


async def test_engine_status_reports_vram() -> None:
    client = FakeComfy().client()
    await client.start()
    status = await engine_status(client)
    await client.close()
    assert status.reachable
    assert status.version == "0.27.0"
    assert status.vram_total_mb == 12 * 1024
    assert status.vram_free_mb == 6 * 1024


def test_parse_outputs_keeps_only_output_files() -> None:
    entry = {
        "outputs": {
            "7": {
                "images": [
                    {"filename": "a_00001_.png", "subfolder": "animesito", "type": "output"},
                    {"filename": "preview.png", "subfolder": "", "type": "temp"},
                ]
            },
            "9": {"gifs": [{"filename": "clip.mp4", "subfolder": "", "type": "output"}]},
        }
    }
    assert parse_outputs(entry) == [
        OutputFile("a_00001_.png", "animesito", "output", MediaKind.IMAGE),
        OutputFile("clip.mp4", "", "output", MediaKind.VIDEO),
    ]


async def test_view_and_upload() -> None:
    fake = FakeComfy()
    fake.files["a.png"] = b"PNGDATA"
    client = fake.client()
    await client.start()
    data = await client.view(OutputFile("a.png", "", "output", MediaKind.IMAGE))
    name = await client.upload_image(b"x", "ref.png")
    await client.interrupt("p9")
    await client.free()
    await client.close()
    assert data == b"PNGDATA"
    assert name == "ref.png"
    assert fake.interrupted == ["p9"]
    assert fake.freed == 1


async def test_events_skip_binary_previews_and_garbage() -> None:
    fake = FakeComfy()
    fake.ws_messages = [
        event("status", status={"exec_info": {"queue_remaining": 1}}),
        b"\x00\x00binary-preview",
        "not json",
        event("progress", value=3, max=20, prompt_id="p1", node="5"),
        event("execution_success", prompt_id="p1"),
    ]
    client = fake.client()
    await client.start()
    events = [item async for item in client.events()]
    await client.close()
    assert [item.type for item in events] == ["status", "progress", "execution_success"]
    assert events[1].prompt_id == "p1"
    assert events[1].data["value"] == 3
