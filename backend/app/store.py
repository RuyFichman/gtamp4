"""Settings the user changes in the UI, kept in the `setting` table (key/value)."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session

from app.config import get_settings
from app.models import Setting


class RadarConfig(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(ge=5, le=24 * 60)
    daily_limit: int = Field(ge=0, le=200)


def get_value(session: Session, key: str) -> str | None:
    row = session.get(Setting, key)
    return row.value if row else None


def set_value(session: Session, key: str, value: str) -> None:
    row = session.get(Setting, key) or Setting(key=key, value=value)
    row.value = value
    session.add(row)
    session.commit()


def get_radar_config(session: Session) -> RadarConfig:
    raw = get_value(session, "radar_config")
    if raw:
        return RadarConfig.model_validate_json(raw)
    s = get_settings()
    return RadarConfig(interval_minutes=s.radar_interval_minutes, daily_limit=s.radar_daily_limit)


def set_radar_config(session: Session, config: RadarConfig) -> None:
    set_value(session, "radar_config", config.model_dump_json())


def get_time(session: Session, key: str) -> datetime | None:
    raw = get_value(session, key)
    return datetime.fromisoformat(raw) if raw else None


def set_time(session: Session, key: str, value: datetime) -> None:
    set_value(session, key, value.isoformat())


class AppConfig(BaseModel):
    """Ajustes tab. Secrets are NOT here: the API key stays in .env."""

    min_clip_s: float = Field(default=12, ge=5, le=60)
    max_clip_s: float = Field(default=75, ge=15, le=180)
    max_clips: int = Field(default=5, ge=1, le=10)
    video_encoder: Literal["auto", "h264_amf", "libx264"] = "auto"
    whisper_model: Literal["tiny", "base", "small", "medium"] = "small"
    model_writer: str = Field(min_length=3)
    model_triage: str = Field(min_length=3)

    @model_validator(mode="after")
    def _min_below_max(self) -> Self:
        if self.min_clip_s >= self.max_clip_s:
            raise ValueError("A duração mínima precisa ser menor que a máxima.")
        return self


def default_app_config() -> AppConfig:
    s = get_settings()
    encoder = s.video_encoder if s.video_encoder in ("h264_amf", "libx264") else "auto"
    return AppConfig(
        video_encoder=encoder, model_writer=s.model_writer, model_triage=s.model_triage
    )


def get_app_config(session: Session) -> AppConfig:
    raw = get_value(session, "app_config")
    if raw:
        return AppConfig.model_validate_json(raw)
    return default_app_config()


def set_app_config(session: Session, config: AppConfig) -> None:
    set_value(session, "app_config", config.model_dump_json())
