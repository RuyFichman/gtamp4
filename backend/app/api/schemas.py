from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, field_serializer

from app.models import Clip, ClipStatus, Job, JobStatus, SourceVideo


class _UtcModel(BaseModel):
    @field_serializer("*", when_used="json")
    def _utc(self, value: object) -> object:
        # SQLite drops tzinfo; everything we store is UTC.
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value


class SourceOut(_UtcModel):
    id: int
    url: str
    title: str
    channel: str
    views: int | None
    views_checked_at: datetime | None

    @classmethod
    def of(cls, v: SourceVideo) -> "SourceOut":
        return cls(
            id=v.id or 0,
            url=v.url,
            title=v.title,
            channel=v.channel,
            views=v.views,
            views_checked_at=v.views_checked_at,
        )


class ClipOut(_UtcModel):
    id: int
    title: str
    description: str
    hashtags: list[str]
    potential: int
    potential_reason: str
    status: ClipStatus
    start_s: float
    end_s: float
    video_url: str | None
    created_at: datetime
    source: SourceOut

    @classmethod
    def of(cls, c: Clip, v: SourceVideo) -> "ClipOut":
        return cls(
            id=c.id or 0,
            title=c.title,
            description=c.description,
            hashtags=c.hashtags,
            potential=c.potential,
            potential_reason=c.potential_reason,
            status=c.status,
            start_s=c.start_s,
            end_s=c.end_s,
            video_url=f"/api/media/clips/{Path(c.file_path).name}" if c.file_path else None,
            created_at=c.created_at,
            source=SourceOut.of(v),
        )


class JobOut(_UtcModel):
    id: int
    kind: str
    status: JobStatus
    progress: float
    message: str
    error: str | None
    title: str | None
    url: str | None
    updated_at: datetime

    @classmethod
    def of(cls, j: Job) -> "JobOut":
        return cls(
            id=j.id or 0,
            kind=j.kind,
            status=j.status,
            progress=j.progress,
            message=j.message,
            error=j.error,
            title=j.payload.get("title"),
            url=j.payload.get("url"),
            updated_at=j.updated_at,
        )


class AddVideoIn(BaseModel):
    url: str


class ClipStatusIn(BaseModel):
    status: ClipStatus
