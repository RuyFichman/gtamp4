"""Transcript sources: YouTube json3 subtitles first, faster-whisper on CPU as fallback."""

from pathlib import Path
from typing import Any

from app.pipeline.types import Segment


def parse_json3(data: dict[str, Any]) -> list[Segment]:
    segments: list[Segment] = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs or "tStartMs" not in event:
            continue
        text = " ".join("".join(s.get("utf8", "") for s in segs).split())
        if not text:
            continue
        start = event["tStartMs"] / 1000
        end = start + event.get("dDurationMs", 0) / 1000
        segments.append(Segment(start=round(start, 2), end=round(end, 2), text=text))
    # auto captions overlap (rolling lines): clip each end to the next start
    for cur, nxt in zip(segments, segments[1:], strict=False):
        cur["end"] = min(cur["end"], nxt["start"]) if nxt["start"] > cur["start"] else cur["end"]
    return segments


def whisper_transcribe(
    video: Path, language: str | None, model_size: str = "small"
) -> tuple[list[Segment], str | None]:
    from faster_whisper import WhisperModel  # heavy import, only when needed

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    raw, info = model.transcribe(str(video), language=language, vad_filter=True)
    segments = [
        Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip()) for s in raw
    ]
    return segments, language or info.language
