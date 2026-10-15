"""Animesito service entry point.

Everything beyond routing -- logging, database, Redis, the job queue, storage,
the ComfyUI client and dispatcher, the localhost guard -- arrives through the
plugin graph in jfast.toml.
"""

from __future__ import annotations

from fastapi import APIRouter

from jfastframework import create_app

from modules.assistant import router as assistant_router
from modules.engine import router as engine_router
from modules.gallery import router as gallery_router
from modules.generation import router as generation_router
from modules.jobs import router as jobs_router
from modules.prompts import router as prompts_router

# [jfast:imports]

ROUTERS: list[APIRouter] = [
    assistant_router,
    engine_router,
    gallery_router,
    generation_router,
    jobs_router,
    prompts_router,
    # [jfast:routers]
]

app = create_app(routers=ROUTERS)
