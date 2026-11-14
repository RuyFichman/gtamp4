import shutil

from fastapi import APIRouter

from app.config import get_settings
from app.pipeline.encoder import pick_encoder

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "ok": True,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "encoder": pick_encoder(),
        "ai": bool(settings.anthropic_api_key),
    }
