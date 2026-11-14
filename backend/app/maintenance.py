"""Disk cleanup: original videos are big (~100 MB each) and only needed while a clip
can still change. The Studio downloads the original again if it is missing."""

from pathlib import Path

from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.models import Clip, ClipStatus, Job, JobStatus, SourceVideo

LIVE = (ClipStatus.PENDING_REVIEW, ClipStatus.APPROVED)


class CleanupPreview(BaseModel):
    files: int
    bytes: int
    blocked: str | None  # why it can't run now


def _deletable(session: Session) -> list[SourceVideo]:
    """Originals on disk whose clips are all decided (posted or rejected)."""
    live = set(session.exec(select(Clip.source_video_id).where(col(Clip.status).in_(LIVE))).all())
    videos = session.exec(select(SourceVideo).where(col(SourceVideo.file_path).is_not(None))).all()
    return [v for v in videos if v.id not in live and Path(v.file_path or "").exists()]


def _blocked(session: Session) -> str | None:
    busy = session.exec(
        select(Job.id).where(col(Job.status).in_([JobStatus.QUEUED, JobStatus.RUNNING]))
    ).first()
    return "Há jobs na fila. Espere terminarem para limpar." if busy else None


def preview(session: Session) -> CleanupPreview:
    videos = _deletable(session)
    return CleanupPreview(
        files=len(videos),
        bytes=sum(Path(v.file_path or "").stat().st_size for v in videos),
        blocked=_blocked(session),
    )


def delete_originals(session: Session) -> CleanupPreview:
    reason = _blocked(session)
    if reason:
        raise RuntimeError(reason)
    freed = preview(session)
    for video in _deletable(session):
        Path(video.file_path or "").unlink(missing_ok=True)
        video.file_path = None
        session.add(video)
    session.commit()
    return freed
