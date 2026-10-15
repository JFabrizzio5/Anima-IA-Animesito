"""Pytest configuration for Animesito.

Its presence at the project root is what puts the root on sys.path, so module
tests import ``modules.<name>`` consistently.

``db_session`` runs repositories against in-memory SQLite: fast, no container,
and the same SQLAlchemy models. PostgreSQL-specific behaviour is covered by the
``integration`` tests against the compose database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from jfastframework.db import Base
from jfastframework.testing import build_test_app, client_for

import modules.gallery.models
import modules.jobs.models
import modules.settings.models  # noqa: F401  -- registers the tables on Base.metadata
from tests.fakes import MemoryDisk


@pytest.fixture
def app() -> FastAPI:
    return build_test_app(plugins=["observability"], app_name="animesito")


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(app) as http_client:
        yield http_client


@pytest.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db_session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        yield session


@pytest.fixture
def disk() -> MemoryDisk:
    return MemoryDisk()
