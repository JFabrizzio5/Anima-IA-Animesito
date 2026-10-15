from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import APIRouter

from jfastframework.testing import build_test_app, client_for

from modules.system.plugin import LocalGuardPlugin

router = APIRouter()


@router.post("/things")
async def create_thing() -> dict[str, bool]:
    return {"ok": True}


@router.get("/things")
async def list_things() -> list[str]:
    return []


@pytest.fixture
async def guarded() -> AsyncIterator[httpx.AsyncClient]:
    app = build_test_app(
        plugins=["observability", "localguard"],
        extra_plugins=[LocalGuardPlugin],
        routers=[router],
        app_name="animesito",
    )
    async with client_for(app) as client:
        yield client


async def test_reads_need_no_header(guarded: httpx.AsyncClient) -> None:
    assert (await guarded.get("/things")).status_code == 200


async def test_writes_need_the_header(guarded: httpx.AsyncClient) -> None:
    assert (await guarded.post("/things")).status_code == 403
    response = await guarded.post("/things", headers={"X-Animesito": "1"})
    assert response.status_code == 200


async def test_foreign_host_is_refused(guarded: httpx.AsyncClient) -> None:
    response = await guarded.get("/things", headers={"Host": "evil.example:7789"})
    assert response.status_code == 400
    ok = await guarded.get("/things", headers={"Host": "localhost:7789"})
    assert ok.status_code == 200


async def test_health_is_exempt(guarded: httpx.AsyncClient) -> None:
    assert (await guarded.get("/health")).status_code == 200
