from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

from app.feedback import RejectReason
from app.models import Account, Clip, ClipStatus, Job, JobStatus, SourceVideo
from app.pipeline.captions import CaptionStyle


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
    reject_reason: str | None = None
    start_s: float
    end_s: float
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    captions: bool = True
    video_url: str | None
    created_at: datetime
    account_id: int | None
    post_url: str | None
    posted_at: datetime | None
    rendering: bool = False  # a Studio re-render is queued/running
    archived: bool = False
    source: SourceOut

    @classmethod
    def of(cls, c: Clip, v: SourceVideo, rendering: bool = False) -> "ClipOut":
        return cls(
            id=c.id or 0,
            title=c.title,
            description=c.description,
            hashtags=c.hashtags,
            potential=c.potential,
            potential_reason=c.potential_reason,
            status=c.status,
            reject_reason=c.reject_reason,
            start_s=c.start_s,
            end_s=c.end_s,
            zoom=c.zoom,
            pan_x=c.pan_x,
            pan_y=c.pan_y,
            captions=c.captions,
            video_url=f"/api/media/clips/{Path(c.file_path).name}" if c.file_path else None,
            created_at=c.created_at,
            account_id=c.account_id,
            post_url=c.post_url,
            posted_at=c.posted_at,
            rendering=rendering,
            archived=c.archived,
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


class ClipArchiveIn(BaseModel):
    archived: bool


class ClipStatusIn(BaseModel):
    status: ClipStatus
    # only used when status == rejected (optional: "recusar sem motivo")
    reject_reason: RejectReason | None = None
    # only used when status == posted
    account_id: int | None = None
    post_url: str | None = None


class RejectReasonOut(BaseModel):
    key: str
    label: str


Platform = Literal["tiktok", "instagram", "youtube", "outra"]


class AccountIn(BaseModel):
    platform: Platform
    handle: str
    name: str = ""
    notes: str = ""


class AccountOut(_UtcModel):
    id: int
    platform: str
    handle: str
    name: str
    notes: str
    posted_count: int
    created_at: datetime

    @classmethod
    def of(cls, a: Account, posted_count: int = 0) -> "AccountOut":
        return cls(
            id=a.id or 0,
            platform=a.platform,
            handle=a.handle,
            name=a.name,
            notes=a.notes,
            posted_count=posted_count,
            created_at=a.created_at,
        )


class Segment(BaseModel):
    start: float
    end: float
    text: str


class StudioOut(_UtcModel):
    clip: ClipOut
    source_video_url: str | None
    duration_s: float | None
    transcript: list[Segment]
    render_job: JobOut | None
    min_s: float
    max_s: float
    frame_url: str | None = None  # frame in use, for the framing preview
    caption_style: CaptionStyle = CaptionStyle()  # for the preview; .enabled is global


class ClipEditIn(BaseModel):
    title: str
    description: str
    hashtags: list[str]
    start_s: float
    end_s: float
    zoom: float = Field(1.0, ge=1.0, le=3.0)
    pan_x: float = Field(0.0, ge=-1.0, le=1.0)
    pan_y: float = Field(0.0, ge=-1.0, le=1.0)
    captions: bool | None = None  # None = keep the clip's


class AutoFrameOut(BaseModel):
    found: bool
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    message: str
