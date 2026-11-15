"""Burned-in TikTok-style captions: word timings (faster-whisper) -> .ass file for ffmpeg.

Pure except `transcribe_words` (ffmpeg + Whisper). Text always stays in the video's language.
"""

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.pipeline.transcribe import decode_audio
from app.pipeline.types import Word

FONTS = ("Arial Black", "Impact", "Segoe UI Black", "Verdana", "Tahoma", "Arial")
Font = Literal["Arial Black", "Impact", "Segoe UI Black", "Verdana", "Tahoma", "Arial"]
HEX = r"^#[0-9a-fA-F]{6}$"

GAP_BREAK_S = 0.7  # a pause this long starts a new caption
HOLD_S = 0.3  # keep the last caption on screen a bit after the word ends


class CaptionStyle(BaseModel):
    """Moldura tab. `enabled` is global; each clip can still turn it off in the Studio."""

    enabled: bool = True
    font: Font = "Arial Black"
    size: int = Field(default=84, ge=40, le=160)
    color: str = Field(default="#FFFFFF", pattern=HEX)
    highlight: str = Field(default="#FFE14D", pattern=HEX)
    outline: int = Field(default=6, ge=0, le=16)
    position_y: float = Field(default=0.62, ge=0.1, le=0.9)  # center of the text, 0 = top
    max_words: int = Field(default=3, ge=1, le=6)
    uppercase: bool = True


def ass_color(hex_color: str) -> str:
    """#RRGGBB -> ASS &H00BBGGRR (alpha first, then blue-green-red)."""
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H00{b}{g}{r}".upper()


def ass_time(t: float) -> str:
    cs = max(0, round(t * 100))
    h, rest = divmod(cs, 360000)
    m, rest = divmod(rest, 6000)
    s, cs = divmod(rest, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean(text: str) -> str:
    # braces and backslashes are ASS override syntax
    return re.sub(r"[{}\\]", "", text).strip()


def clip_words(words: list[Word], start: float, end: float) -> list[Word]:
    """Words inside [start, end], shifted so the clip starts at 0."""
    out: list[Word] = []
    for w in words:
        text = _clean(w["word"])
        if not text or w["end"] <= start or w["start"] >= end:
            continue
        s, e = max(w["start"], start) - start, min(w["end"], end) - start
        out.append(Word(start=round(s, 3), end=round(max(e, s + 0.05), 3), word=text))
    return out


def chunk_words(words: list[Word], max_words: int) -> list[list[Word]]:
    """Group words into short captions: max N words, break on long pauses and sentence ends."""
    chunks: list[list[Word]] = []
    for w in words:
        cur = chunks[-1] if chunks else None
        if (
            cur is None
            or len(cur) >= max_words
            or w["start"] - cur[-1]["end"] > GAP_BREAK_S
            or cur[-1]["word"].endswith((".", "!", "?", "…"))
        ):
            chunks.append([w])
        else:
            cur.append(w)
    return chunks


def build_ass(words: list[Word], duration: float, style: CaptionStyle) -> str:
    """Words already relative to the clip (see clip_words). One event per spoken word: the
    whole caption is shown with that word highlighted (bigger, other color)."""
    y = round(1920 * style.position_y)
    hi = ass_color(style.highlight)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{style.font},{style.size},{ass_color(style.color)},{hi},&H00000000,"
        f"&H80000000,-1,0,0,0,100,100,0,0,1,{style.outline},2,5,60,60,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    chunks = chunk_words(words, style.max_words)
    for ci, chunk in enumerate(chunks):
        next_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else duration
        chunk_end = min(chunk[-1]["end"] + HOLD_S, next_start, duration)
        texts = [w["word"].upper() if style.uppercase else w["word"] for w in chunk]
        for i, w in enumerate(chunk):
            ev_start = w["start"]
            ev_end = chunk[i + 1]["start"] if i + 1 < len(chunk) else chunk_end
            if ev_end <= ev_start:
                continue
            parts = [
                f"{{\\c{hi}\\fscx112\\fscy112}}{t}{{\\r}}" if j == i else t
                for j, t in enumerate(texts)
            ]
            lines.append(
                f"Dialogue: 0,{ass_time(ev_start)},{ass_time(ev_end)},Cap,,0,0,0,,"
                f"{{\\pos(540,{y})}}" + " ".join(parts)
            )
    return "\n".join(lines) + "\n"


def whisper_language(language: str | None) -> str | None:
    """yt-dlp gives 'pt-BR', 'en-US'...; Whisper wants 'pt', 'en'."""
    from faster_whisper.tokenizer import _LANGUAGE_CODES

    code = (language or "").split("-")[0].split("_")[0].lower()
    return code if code in _LANGUAGE_CODES else None


def load_whisper(model_size: str) -> Any:
    from faster_whisper import WhisperModel  # heavy import, only when needed

    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe_words(
    model: Any, video: Path, start: float, end: float, language: str | None
) -> list[Word]:
    """Word timings for [start, end] of the source video, in source-video seconds."""
    audio = decode_audio(video, start, end)
    raw, _info = model.transcribe(
        audio, language=whisper_language(language), word_timestamps=True, vad_filter=True
    )
    words: list[Word] = []
    for seg in raw:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(
                    Word(start=round(start + w.start, 3), end=round(start + w.end, 3), word=text)
                )
    return words
