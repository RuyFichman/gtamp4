from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from app import frames
from app.db import get_session
from app.models import FrameTemplate

router = APIRouter(prefix="/api/frames", tags=["frames"])
SessionDep = Annotated[Session, Depends(get_session)]


class FrameOut(BaseModel):
    id: int
    name: str
    url: str
    is_default: bool
    width: int | None
    height: int | None


class FramesOut(BaseModel):
    frames: list[FrameOut]
    live_clips: int  # pending + approved clips a re-render would touch


class DefaultIn(BaseModel):
    frame_id: int | None  # None = no frame


def _out(frame: FrameTemplate) -> FrameOut:
    path = Path(frame.overlay_path)
    size = frames.png_size(path)
    return FrameOut(
        id=frame.id or 0,
        name=frame.name,
        url=f"/api/media/frames/{path.name}",
        is_default=frame.is_default,
        width=size[0] if size else None,
        height=size[1] if size else None,
    )


def _list(session: Session) -> FramesOut:
    rows = session.exec(select(FrameTemplate).order_by(FrameTemplate.id)).all()
    return FramesOut(frames=[_out(f) for f in rows], live_clips=len(frames.live_clips(session)))


@router.get("")
def list_frames(session: SessionDep) -> FramesOut:
    return _list(session)


@router.post("")
async def upload_frame(
    session: SessionDep,
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> FramesOut:
    data = await file.read(frames.MAX_BYTES + 1)
    try:
        frames.add_frame(session, name, data)
    except frames.FrameError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _list(session)


@router.put("/default")
def set_default(body: DefaultIn, session: SessionDep) -> FramesOut:
    try:
        frames.set_default(session, body.frame_id)
    except LookupError as exc:
        raise HTTPException(404, "Moldura não encontrada.") from exc
    return _list(session)


@router.delete("/{frame_id}")
def delete_frame(frame_id: int, session: SessionDep) -> FramesOut:
    try:
        frames.delete_frame(session, frame_id)
    except LookupError as exc:
        raise HTTPException(404, "Moldura não encontrada.") from exc
    return _list(session)


class RerenderOut(BaseModel):
    queued: int


@router.post("/rerender")
def rerender(session: SessionDep) -> RerenderOut:
    return RerenderOut(queued=frames.rerender_live(session))
