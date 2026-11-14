from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # backend/.env wins over the repo-root .env when both exist
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore"
    )

    anthropic_api_key: str = ""
    model_triage: str = "claude-haiku-5-5"
    model_writer: str = "claude-sonnet-5-5"

    data_dir: Path = PROJECT_DIR / "data"
    radar_interval_minutes: int = 5
    video_encoder: str = "auto"  # auto | h264_amf | libx264

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def videos_dir(self) -> Path:
        return self.data_dir / "videos"

    @property
    def clips_dir(self) -> Path:
        return self.data_dir / "clips"

    @property
    def frames_dir(self) -> Path:
        return self.data_dir / "frames"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.videos_dir, self.clips_dir, self.frames_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
