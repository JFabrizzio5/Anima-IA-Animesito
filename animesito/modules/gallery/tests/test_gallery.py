from __future__ import annotations

import io

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from jfastframework.errors import NotFoundError

from modules.gallery.models import NewMedia
from modules.gallery.public import generated_by_app, read_file, save_media
from modules.gallery.repositories import GalleryRepository
from modules.gallery.services import GalleryService
from shared.enums import MediaKind, MediaSource
from tests.fakes import MemoryDisk


def png(width: int = 640, height: int = 960, color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def media(data: bytes, **overrides: object) -> NewMedia:
    values: dict[str, object] = {
        "data": data,
        "filename": "img_00001_.png",
        "kind": MediaKind.IMAGE,
        "source": MediaSource.GENERATED,
        "job_id": "job1",
        "prompt": "1girl, silver hair, night city",
        "model": "ckpt:wai.safetensors",
        "seed": 42,
    }
    values.update(overrides)
    return NewMedia(**values)  # type: ignore[arg-type]


@pytest.fixture
def service(db_session: AsyncSession, disk: MemoryDisk) -> GalleryService:
    return GalleryService(GalleryRepository(db_session), disk)


async def test_save_stores_file_thumbnail_and_metadata(
    service: GalleryService, disk: MemoryDisk
) -> None:
    saved = await service.save(media(png()))
    assert (saved.width, saved.height) == (640, 960)
    assert saved.mime == "image/png"
    assert saved.file_key.startswith("gallery/") and saved.file_key.endswith(".png")
    assert saved.thumb_key is not None and saved.thumb_key.endswith(".webp")
    with Image.open(io.BytesIO(disk.files[saved.thumb_key])) as thumb:
        assert max(thumb.size) == 384
    assert len(saved.sha256) == 64


async def test_search_by_prompt_and_favorite(service: GalleryService) -> None:
    first = await service.save(media(png(color="red")))
    await service.save(media(png(color="blue"), prompt="1boy, forest"))
    await service.set_favorite(first.id, True)

    items, total = await service.search(query="silver")
    assert total == 1 and items[0].id == first.id
    items, total = await service.search(favorite=True)
    assert [item.id for item in items] == [first.id]
    _, total = await service.search()
    assert total == 2


async def test_delete_removes_files_then_row(service: GalleryService, disk: MemoryDisk) -> None:
    saved = await service.save(media(png()))
    await service.delete(saved.id)
    assert disk.files == {}
    with pytest.raises(NotFoundError):
        await service.get(saved.id)


async def test_provenance_only_for_generated_files(
    db_session: AsyncSession, disk: MemoryDisk
) -> None:
    generated = png(color="green")
    uploaded = png(color="yellow")
    await save_media(db_session, disk, tenant_id=None, media=media(generated))
    await save_media(
        db_session, disk, tenant_id=None, media=media(uploaded, source=MediaSource.UPLOAD)
    )
    assert await generated_by_app(db_session, disk, tenant_id=None, data=generated) is True
    assert await generated_by_app(db_session, disk, tenant_id=None, data=uploaded) is False
    assert await generated_by_app(db_session, disk, tenant_id=None, data=b"other") is False


async def test_read_file_round_trip(db_session: AsyncSession, disk: MemoryDisk) -> None:
    data = png()
    summary = await save_media(db_session, disk, tenant_id=None, media=media(data))
    found = await read_file(db_session, disk, tenant_id=None, generation_id=summary.id)
    assert found is not None and found[1] == data
    assert await read_file(db_session, disk, tenant_id=None, generation_id=999) is None


async def test_video_is_stored_without_thumbnail(service: GalleryService) -> None:
    saved = await service.save(
        media(b"\x00\x00\x00 ftypmp42", filename="clip.mp4", kind=MediaKind.VIDEO)
    )
    assert saved.mime == "video/mp4" and saved.thumb_key is None
