from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app import maintenance
from app.config import BACKEND_DIR, PROJECT_DIR, get_settings
from app.db import get_session
from app.pipeline.encoder import hw_encoder_works
from app.store import AppConfig, default_app_config, get_app_config, set_app_config

router = APIRouter(prefix="/api", tags=["settings"])
SessionDep = Annotated[Session, Depends(get_session)]


class SettingsOut(BaseModel):
    config: AppConfig
    defaults: AppConfig
    ai_key_set: bool  # never the key itself
    env_files: list[str]
    amf_available: bool
    data_dir: str


def _out(session: Session) -> SettingsOut:
    env_files = [p for p in (PROJECT_DIR / ".env", BACKEND_DIR / ".env") if p.exists()]
    return SettingsOut(
        config=get_app_config(session),
        defaults=default_app_config(),
        ai_key_set=bool(get_settings().anthropic_api_key),
        env_files=[str(p) for p in env_files],
        amf_available=hw_encoder_works(),
        data_dir=str(get_settings().data_dir),
    )


@router.get("/settings")
def get_app_settings(session: SessionDep) -> SettingsOut:
    return _out(session)


@router.put("/settings")
def put_app_settings(body: AppConfig, session: SessionDep) -> SettingsOut:
    set_app_config(session, body)
    return _out(session)


@router.get("/maintenance/originals")
def originals_preview(session: SessionDep) -> maintenance.CleanupPreview:
    return maintenance.preview(session)


@router.post("/maintenance/originals/delete")
def originals_delete(session: SessionDep) -> maintenance.CleanupPreview:
    try:
        return maintenance.delete_originals(session)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
