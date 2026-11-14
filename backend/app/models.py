from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import UniqueConstraint
from sqlmodel import JSON, Column, Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class ClipStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    POSTED = "posted"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class SourceVideo(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    youtube_id: str = Field(index=True, unique=True)
    url: str
    title: str = ""
    channel: str = ""
    language: str | None = None
    duration_s: float | None = None
    description: str = ""
    views: int | None = None
    views_checked_at: datetime | None = None
    file_path: str | None = None
    transcript: list[dict[str, Any]] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Clip(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    source_video_id: int = Field(foreign_key="sourcevideo.id", index=True)
    start_s: float
    end_s: float
    title: str = ""
    description: str = ""
    hashtags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    potential: int = 0
    potential_reason: str = ""
    file_path: str | None = None
    status: ClipStatus = Field(default=ClipStatus.PENDING_REVIEW, index=True)
    account_id: int | None = Field(default=None, foreign_key="account.id")
    post_url: str | None = None
    posted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Job(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: JobStatus = Field(default=JobStatus.QUEUED, index=True)
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    attempts: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    platform: str  # tiktok | instagram
    handle: str
    name: str = ""
    notes: str = ""
    warmup_started_on: date | None = None  # local date; None = not warming up
    created_at: datetime = Field(default_factory=utcnow)


class WarmupCheck(SQLModel, table=True):
    """One ticked item of the manual warm-up checklist (the app never touches the account)."""

    __table_args__ = (UniqueConstraint("account_id", "day", "task_key"),)

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="account.id", index=True)
    day: date
    task_key: str
    created_at: datetime = Field(default_factory=utcnow)


class FrameTemplate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    overlay_path: str
    is_default: bool = False


class RadarQuery(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kind: str = "search"  # search | channel
    query: str
    enabled: bool = True
    last_run_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class CandidateStatus(StrEnum):
    REJECTED = "rejected"  # filtered out (pre-filter or triage)
    WAITING = "waiting"  # passed triage, waiting for the daily quota
    SENT = "sent"  # process_video job enqueued


class RadarCandidate(SQLModel, table=True):
    """Every video the Radar has seen, so it is never evaluated twice."""

    id: int | None = Field(default=None, primary_key=True)
    youtube_id: str = Field(index=True, unique=True)
    url: str
    title: str = ""
    channel: str = ""
    duration_s: float | None = None
    views: int | None = None
    query_id: int | None = None
    status: CandidateStatus = Field(default=CandidateStatus.REJECTED, index=True)
    reason: str = ""
    job_id: int | None = None
    found_at: datetime = Field(default_factory=utcnow)
    sent_at: datetime | None = None


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
