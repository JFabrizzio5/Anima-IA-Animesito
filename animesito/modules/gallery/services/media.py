"""Blocking media helpers: hashing, probing, thumbnails. Call via a thread."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import PurePosixPath

from PIL import Image, UnidentifiedImageError

from shared.enums import MediaKind

THUMB_EDGE = 384

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}


@dataclass(frozen=True, slots=True)
class Probe:
    sha256: str
    mime: str
    suffix: str
    width: int | None
    height: int | None
    thumbnail: bytes | None


def suffix_of(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    return suffix if suffix in _MIME_BY_SUFFIX else ".bin"


def probe(data: bytes, filename: str, kind: MediaKind) -> Probe:
    suffix = suffix_of(filename)
    mime = _MIME_BY_SUFFIX.get(suffix, "application/octet-stream")
    digest = hashlib.sha256(data).hexdigest()
    if kind is not MediaKind.IMAGE:
        return Probe(digest, mime, suffix, None, None, None)
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            thumb = image.convert("RGB") if image.mode not in ("RGB", "RGBA") else image.copy()
    except (UnidentifiedImageError, OSError):
        return Probe(digest, mime, suffix, None, None, None)
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE))
    buffer = io.BytesIO()
    thumb.save(buffer, format="WEBP", quality=82, method=4)
    return Probe(digest, mime, suffix, width, height, buffer.getvalue())


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
