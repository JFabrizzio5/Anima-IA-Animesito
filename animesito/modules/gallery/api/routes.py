"""HTTP layer for the Gallery module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from jfastframework.app import get_context
from jfastframework.plugins.builtin.database import DbSession
from jfastframework.storage.base import StorageBackend

from shared.enums import MediaKind, MediaSource

from ..models import GalleryPage, Generation, GenerationRead, GenerationUpdate
from ..repositories import GalleryRepository
from ..services import GalleryService

router = APIRouter(prefix="/gallery", tags=["gallery"])


async def get_service(request: Request, session: DbSession) -> GalleryService:
    tenant_id = getattr(request.state, "tenant_id", None)
    disk: StorageBackend = get_context(request.app).require("storage").disk()
    return GalleryService(GalleryRepository(session, tenant_id=tenant_id), disk)


def to_read(service: GalleryService, generation: Generation) -> GenerationRead:
    return GenerationRead(
        id=generation.id,
        job_id=generation.job_id,
        kind=MediaKind(generation.kind),
        source=MediaSource(generation.source),
        url=service.url(generation.file_key) or "",
        thumb_url=service.url(generation.thumb_key),
        mime=generation.mime,
        width=generation.width,
        height=generation.height,
        size_bytes=generation.size_bytes,
        sha256=generation.sha256,
        prompt=generation.prompt,
        negative=generation.negative,
        model=generation.model,
        seed=generation.seed,
        params=generation.params,
        adult=generation.adult,
        favorite=generation.favorite,
        created_at=generation.created_at,
    )


@router.get("", response_model=GalleryPage, summary="Search the gallery, newest first")
async def list_gallery(
    q: str | None = Query(None, max_length=200),
    favorite: bool | None = Query(None),
    kind: MediaKind | None = Query(None),
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: GalleryService = Depends(get_service),
) -> GalleryPage:
    items, total = await service.search(
        query=q, favorite=favorite, kind=kind, limit=limit, offset=offset
    )
    return GalleryPage(
        items=[to_read(service, item) for item in items], total=total, limit=limit, offset=offset
    )


@router.get("/{generation_id}", response_model=GenerationRead, summary="One gallery item")
async def get_generation(
    generation_id: int, service: GalleryService = Depends(get_service)
) -> GenerationRead:
    return to_read(service, await service.get(generation_id))


@router.patch("/{generation_id}", response_model=GenerationRead, summary="Mark or unmark favorite")
async def update_generation(
    generation_id: int,
    payload: GenerationUpdate,
    service: GalleryService = Depends(get_service),
) -> GenerationRead:
    generation = await service.get(generation_id)
    if payload.favorite is not None:
        generation = await service.set_favorite(generation_id, payload.favorite)
    return to_read(service, generation)


@router.delete(
    "/{generation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a gallery item and its files",
)
async def delete_generation(
    generation_id: int, service: GalleryService = Depends(get_service)
) -> None:
    await service.delete(generation_id)
