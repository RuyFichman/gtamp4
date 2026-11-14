"""Single place that decides which H.264 encoder ffmpeg uses (AMD AMF with libx264 fallback)."""

from functools import lru_cache

from app.config import get_settings
from app.pipeline.proc import CommandError, run

HW_ENCODER = "h264_amf"
SW_ENCODER = "libx264"


@lru_cache
def hw_encoder_works() -> bool:
    try:
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=0.2:size=320x240",
                "-c:v",
                HW_ENCODER,
                "-f",
                "null",
                "-",
            ]
        )
    except (CommandError, FileNotFoundError):
        return False
    return True


def pick_encoder() -> str:
    choice = get_settings().video_encoder
    if choice in (HW_ENCODER, SW_ENCODER):
        return choice
    return HW_ENCODER if hw_encoder_works() else SW_ENCODER


def encoder_args(encoder: str) -> list[str]:
    if encoder == HW_ENCODER:
        return [
            "-c:v",
            HW_ENCODER,
            "-quality",
            "quality",
            "-rc",
            "cqp",
            "-qp_i",
            "20",
            "-qp_p",
            "22",
        ]
    return ["-c:v", SW_ENCODER, "-preset", "medium", "-crf", "20"]
