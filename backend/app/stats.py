"""Numbers for the Painel tab. Data is small (one user), so aggregation happens in Python."""

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from app.config import get_settings
from app.jobs.radar_jobs import sent_last_24h
from app.models import (
    Account,
    CandidateStatus,
    Clip,
    ClipStatus,
    Job,
    JobStatus,
    RadarCandidate,
    SourceVideo,
    utcnow,
)
from app.store import get_radar_config, get_time

DAYS = 14


class ClipCounts(BaseModel):
    pending_review: int = 0
    approved: int = 0
    rejected: int = 0
    posted: int = 0
    total: int = 0


class Day(BaseModel):
    date: date
    generated: int
    posted: int


class AccountStat(BaseModel):
    id: int
    handle: str
    platform: str
    posted: int
    last_posted_at: datetime | None


class JobCounts(BaseModel):
    queued: int
    running: int
    failed: int
    done_24h: int


class RadarStat(BaseModel):
    enabled: bool
    sent_24h: int
    daily_limit: int
    found_24h: int
    waiting: int
    last_scan_at: datetime | None


class DiskStat(BaseModel):
    videos_bytes: int
    videos_files: int
    clips_bytes: int


class Stats(BaseModel):
    clips: ClipCounts
    approval_rate: float | None  # (approved + posted) / reviewed
    avg_potential_kept: float | None
    avg_potential_rejected: float | None
    source_videos: int
    days: list[Day]
    accounts: list[AccountStat]
    jobs: JobCounts
    radar: RadarStat
    disk: DiskStat


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite drops tzinfo; we store UTC


def _local_day(dt: datetime) -> date:
    return _aware(dt).astimezone().date()  # the machine's timezone, like the user sees it


def _dir_size(path: Path) -> tuple[int, int]:
    files = [p for p in path.glob("*") if p.is_file()] if path.exists() else []
    return sum(p.stat().st_size for p in files), len(files)


def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _days(clips: list[Clip], today: date) -> list[Day]:
    first = today - timedelta(days=DAYS - 1)
    generated = Counter(_local_day(c.created_at) for c in clips)
    posted = Counter(_local_day(c.posted_at) for c in clips if c.posted_at)
    return [
        Day(date=d, generated=generated[d], posted=posted[d])
        for d in (first + timedelta(days=i) for i in range(DAYS))
    ]


def _accounts(session: Session, clips: list[Clip]) -> list[AccountStat]:
    posted = [c for c in clips if c.status == ClipStatus.POSTED and c.account_id]
    out = []
    for a in session.exec(select(Account)).all():
        mine = [c.posted_at for c in posted if c.account_id == a.id and c.posted_at]
        out.append(
            AccountStat(
                id=a.id or 0,
                handle=a.handle,
                platform=a.platform,
                posted=len([c for c in posted if c.account_id == a.id]),
                last_posted_at=_aware(max(mine)) if mine else None,
            )
        )
    return sorted(out, key=lambda a: -a.posted)


def _jobs(session: Session) -> JobCounts:
    by_status = Counter(session.exec(select(Job.status)).all())
    done_24h = session.exec(
        select(func.count())
        .select_from(Job)
        .where(Job.status == JobStatus.DONE, col(Job.updated_at) >= utcnow() - timedelta(hours=24))
    ).one()
    return JobCounts(
        queued=by_status[JobStatus.QUEUED],
        running=by_status[JobStatus.RUNNING],
        failed=by_status[JobStatus.FAILED],
        done_24h=done_24h,
    )


def _radar(session: Session) -> RadarStat:
    config = get_radar_config(session)
    found_24h = session.exec(
        select(func.count())
        .select_from(RadarCandidate)
        .where(col(RadarCandidate.found_at) >= utcnow() - timedelta(hours=24))
    ).one()
    waiting = session.exec(
        select(func.count())
        .select_from(RadarCandidate)
        .where(RadarCandidate.status == CandidateStatus.WAITING)
    ).one()
    return RadarStat(
        enabled=config.enabled,
        sent_24h=sent_last_24h(session),
        daily_limit=config.daily_limit,
        found_24h=found_24h,
        waiting=waiting,
        last_scan_at=get_time(session, "radar_last_scan_at"),
    )


def compute(session: Session, today: date | None = None) -> Stats:
    clips = list(session.exec(select(Clip)).all())
    counts = ClipCounts(total=len(clips), **Counter(str(c.status) for c in clips))
    kept = [c.potential for c in clips if c.status in (ClipStatus.APPROVED, ClipStatus.POSTED)]
    rejected = [c.potential for c in clips if c.status == ClipStatus.REJECTED]
    reviewed = len(kept) + len(rejected)
    settings = get_settings()
    videos_bytes, videos_files = _dir_size(settings.videos_dir)
    clips_bytes, _ = _dir_size(settings.clips_dir)
    return Stats(
        clips=counts,
        approval_rate=round(len(kept) / reviewed, 3) if reviewed else None,
        avg_potential_kept=_avg(kept),
        avg_potential_rejected=_avg(rejected),
        source_videos=session.exec(select(func.count()).select_from(SourceVideo)).one(),
        days=_days(clips, today or datetime.now().astimezone().date()),
        accounts=_accounts(session, clips),
        jobs=_jobs(session),
        radar=_radar(session),
        disk=DiskStat(
            videos_bytes=videos_bytes, videos_files=videos_files, clips_bytes=clips_bytes
        ),
    )
