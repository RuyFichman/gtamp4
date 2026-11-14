import shutil
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.pipeline.encoder import pick_encoder
from app.store import get_app_config

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(session: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
    settings = get_settings()
    return {
        "ok": True,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "encoder": pick_encoder(get_app_config(session).video_encoder),
        "ai": bool(settings.anthropic_api_key),
    }
