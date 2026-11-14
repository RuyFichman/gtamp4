import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, col, select

from app.api.schemas import ClipOut, ClipStatusIn
from app.db import get_session
from app.models import Clip, ClipStatus, SourceVideo, utcnow

router = APIRouter(prefix="/api/clips", tags=["clips"])
SessionDep = Annotated[Session, Depends(get_session)]

SORTS = {
    "potential": col(Clip.potential).desc(),
    "recent": col(Clip.id).desc(),
    "views": col(SourceVideo.views).desc(),
}


@router.get("")
def list_clips(
    session: SessionDep,
    status: ClipStatus = ClipStatus.PENDING_REVIEW,
    sort: Literal["potential", "recent", "views"] = "potential",
) -> list[ClipOut]:
    rows = session.exec(
        select(Clip, SourceVideo)
        .join(SourceVideo, col(Clip.source_video_id) == col(SourceVideo.id))
        .where(Clip.status == status)
        .order_by(SORTS[sort], col(Clip.id).desc())
    ).all()
    return [ClipOut.of(c, v) for c, v in rows]


@router.post("/{clip_id}/status")
def set_status(clip_id: int, body: ClipStatusIn, session: SessionDep) -> ClipOut:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Corte não encontrado.")
    clip.status = body.status
    clip.posted_at = utcnow() if body.status == ClipStatus.POSTED else None
    session.add(clip)
    session.commit()
    session.refresh(clip)
    video = session.get(SourceVideo, clip.source_video_id)
    assert video is not None
    return ClipOut.of(clip, video)


@router.get("/{clip_id}/download")
def download_clip(clip_id: int, session: SessionDep) -> FileResponse:
    clip = session.get(Clip, clip_id)
    if clip is None or not clip.file_path or not Path(clip.file_path).exists():
        raise HTTPException(404, "Arquivo do corte não encontrado.")
    slug = re.sub(r"[^\w\- ]+", "", clip.title).strip()[:60] or f"corte-{clip.id}"
    return FileResponse(clip.file_path, media_type="video/mp4", filename=f"{slug}.mp4")
