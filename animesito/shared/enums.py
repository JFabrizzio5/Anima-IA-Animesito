"""Vocabulary more than one module speaks.

Values are the wire format: stored in columns, serialised to JSON, read by the
frontend. Rename a member freely; changing a value is a data migration.
"""

from __future__ import annotations

from enum import StrEnum


class JobKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    UPSCALE = "upscale"
    TRAIN = "train"


class JobStatus(StrEnum):
    QUEUED = "queued"
    SUBMITTED = "submitted"
    RUNNING = "running"
    INGESTING = "ingesting"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED)


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class MediaSource(StrEnum):
    """Where a gallery file came from. Only GENERATED counts as app provenance."""

    GENERATED = "generated"
    UPLOAD = "upload"
    IMPORT = "import"
