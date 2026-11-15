"""Moldura tab: style of the burned-in captions (global; each clip can turn them off)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.pipeline.captions import FONTS, CaptionStyle
from app.store import get_caption_style, set_caption_style

router = APIRouter(prefix="/api/captions", tags=["captions"])
SessionDep = Annotated[Session, Depends(get_session)]


class CaptionsOut(BaseModel):
    style: CaptionStyle
    defaults: CaptionStyle
    fonts: list[str]


def _out(session: Session) -> CaptionsOut:
    return CaptionsOut(style=get_caption_style(session), defaults=CaptionStyle(), fonts=list(FONTS))


@router.get("")
def get_captions(session: SessionDep) -> CaptionsOut:
    return _out(session)


@router.put("")
def put_captions(body: CaptionStyle, session: SessionDep) -> CaptionsOut:
    set_caption_style(session, body)
    return _out(session)
