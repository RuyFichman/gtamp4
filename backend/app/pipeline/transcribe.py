"""Transcript sources: YouTube json3 subtitles first, faster-whisper on CPU as fallback."""

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from app.pipeline import speech
from app.pipeline.proc import CommandError
from app.pipeline.types import Segment

WHISPER_RATE = 16000


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
    # only now drop "[Music]" & co.: a line before the music still ends where the music starts
    return speech.clean_segments(segments)


def whisper_transcribe(
    video: Path, language: str | None, model_size: str = "small"
) -> tuple[list[Segment], str | None]:
    from faster_whisper import WhisperModel  # heavy import, only when needed

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    raw, info = model.transcribe(decode_audio(video), language=language, vad_filter=True)
    segments = [
        Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip()) for s in raw
    ]
    # Whisper writes "♪" or "[Música]" over music now and then
    return speech.clean_segments(segments), language or info.language


def decode_audio(video: Path, start: float | None = None, end: float | None = None) -> np.ndarray:
    """Mono float32 PCM at 16 kHz via ffmpeg, as Whisper expects. Decoding ourselves avoids
    faster-whisper's PyAV path, which breaks with newer `av` releases (metadata_errors)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if start is not None and end is not None:
        cmd += ["-ss", f"{start:.2f}", "-t", f"{end - start:.2f}"]
    cmd += ["-i", str(video), "-vn", "-ac", "1", "-ar", str(WHISPER_RATE), "-f", "s16le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.decode("utf-8", "replace").strip().splitlines()[-15:])
        raise CommandError(f"ffmpeg saiu com código {proc.returncode}:\n{tail}")
    return np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
