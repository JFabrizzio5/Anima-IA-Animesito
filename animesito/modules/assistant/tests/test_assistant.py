from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from jfastframework.errors import ValidationError

from modules.assistant.services import EnhanceError, OllamaClient, enhance, parse_reply


def ollama(reply: dict[str, Any] | str, seen: list[dict[str, Any]] | None = None) -> OllamaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            if seen is not None:
                seen.append(body)
            content = reply if isinstance(reply, str) else json.dumps(reply)
            return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "dolphin-llama3:latest"}]})
        if request.url.path == "/api/generate":
            if seen is not None:
                seen.append(json.loads(request.content))
            return httpx.Response(200, json={"done": True})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "dolphin-llama3:latest",
                            "size": 4661235994,
                            "details": {"parameter_size": "8B"},
                            "capabilities": ["completion"],
                        },
                        {
                            "name": "nomic-embed-text:latest",
                            "size": 274302450,
                            "details": {},
                            "capabilities": ["embedding"],
                        },
                    ]
                },
            )
        return httpx.Response(404)

    return OllamaClient("http://ollama.test", transport=httpx.MockTransport(handler))


def test_parse_reply_cleans_tags() -> None:
    tags, negative = parse_reply(
        json.dumps(
            {
                "tags": ["1girl", "masterpiece", "Silver_Hair", "silver hair", " rooftop ", 7],
                "negative": ["blurry", "lowres"],
            }
        )
    )
    assert tags == ["1girl", "silver hair", "rooftop"]
    assert negative == ["blurry", "lowres"]


@pytest.mark.parametrize("raw", ["not json", "[]", json.dumps({"tags": []})])
def test_parse_reply_refuses_garbage(raw: str) -> None:
    with pytest.raises(EnhanceError):
        parse_reply(raw)


async def test_enhance_sends_json_format_and_unloads_after() -> None:
    seen: list[dict[str, Any]] = []
    client = ollama({"tags": ["1girl", "red hair", "kimono"], "negative": ["blurry"]}, seen)
    await client.start()
    result = await enhance(
        client, model="dolphin-llama3:latest", prompt="chica pelirroja en kimono", adult=False
    )
    await client.close()
    assert result.prompt == "1girl, red hair, kimono" and result.negative == "blurry"
    request = seen[0]
    assert (
        request["format"] == "json" and request["keep_alive"] == "0" and request["stream"] is False
    )
    assert "safe for work" in request["messages"][0]["content"]


async def test_enhance_output_goes_through_the_policy() -> None:
    client = ollama({"tags": ["1girl", "nude", "kitagawa marin"]})
    await client.start()
    with pytest.raises(ValidationError):
        await enhance(client, model="m", prompt="x", adult=True)
    with pytest.raises(ValidationError):
        await enhance(
            client, model="m", prompt="x", adult=True, extra_minor_characters=["kitagawa marin"]
        )
    await client.close()


async def test_learned_minor_names_are_refused() -> None:
    client = ollama({"tags": ["1girl", "obscure hero", "nude"]})
    await client.start()
    ok = await enhance(client, model="m", prompt="x", adult=True)
    assert "obscure hero" in ok.prompt
    with pytest.raises(ValidationError):
        await enhance(
            client, model="m", prompt="x", adult=True, extra_minor_characters=["obscure hero"]
        )
    await client.close()


async def test_models_and_unload() -> None:
    seen: list[dict[str, Any]] = []
    client = ollama({"tags": ["x"]}, seen)
    await client.start()
    models = await client.models()
    unloaded = await client.unload_all()
    await client.close()
    assert [model.is_embedding for model in models] == [False, True]
    assert models[0].size_gb == 4.3
    assert unloaded == ["dolphin-llama3:latest"]
    assert seen[-1] == {"model": "dolphin-llama3:latest", "keep_alive": 0}
