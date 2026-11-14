from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.schemas import AddVideoIn, JobOut, SourceOut
from app.db import get_session
from app.jobs import queue
from app.jobs.handlers import PROCESS_VIDEO
from app.models import SourceVideo, utcnow
from app.pipeline import download

router = APIRouter(prefix="/api/videos", tags=["videos"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", status_code=201)
def add_video(body: AddVideoIn, session: SessionDep) -> JobOut:
    youtube_id = download.parse_youtube_id(body.url)
    if youtube_id is None:
        raise HTTPException(400, "Isso não parece um link de vídeo do YouTube.")
    job = queue.enqueue(session, PROCESS_VIDEO, {"url": download.canonical_url(youtube_id)})
    return JobOut.of(job)


@router.post("/{video_id}/refresh-views")
def refresh_views(video_id: int, session: SessionDep) -> SourceOut:
    video = session.get(SourceVideo, video_id)
    if video is None:
        raise HTTPException(404, "Vídeo não encontrado.")
    try:
        video.views = download.fetch_views(video.url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Não consegui consultar o YouTube: {exc}") from exc
    video.views_checked_at = utcnow()
    session.add(video)
    session.commit()
    session.refresh(video)
    return SourceOut.of(video)
