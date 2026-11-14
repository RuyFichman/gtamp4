"""Settings the user changes in the UI, kept in the `setting` table (key/value)."""

from datetime import datetime

from pydantic import BaseModel, Field
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
