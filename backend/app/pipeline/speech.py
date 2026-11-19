"""Is someone talking? Pure helpers (no I/O) over transcripts and Whisper words.

A gameplay video's audio is mostly game: music, engines, gunfire, cutscene dialogue. These
helpers take non-speech cues out of YouTube captions ("[Music]", "♪") and measure how much
of a whole video, or of a clip window, is speech. They cannot tell the commentator apart from
in-game dialogue (cutscenes, NPCs, radio): a no-commentary video full of cutscenes has plenty
of "speech". That call is the AI's (`score.ClipPlan.has_commentary`); these numbers only catch
the obvious cases cheaply (long silent stretches, a video that is barely spoken).

Thresholds were calibrated on the editor's approved clips (all of them commented speech) and
sit well below the lowest value seen there.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.pipeline.types import Segment, Word

# --- video level: checked on the whole transcript before any clip is chosen ---------------
# Calibrated on the 14 videos with approved clips: coverage 0.45 to 1.00, 43 to 230 words per
# minute (the lowest are commented gameplay / reactions, with game audio between the lines).
# Below these, the video is barely spoken (trailer, music, driving, a walkthrough without
# cutscenes). A no-commentary video full of cutscenes still passes: has_commentary catches it.
# Share of the video covered by speech segments (merged).
VIDEO_MIN_COVERAGE = 0.25
# Words per minute over the whole video.
VIDEO_MIN_WPM = 25.0

# --- clip level: checked on the Whisper words of each clip after its edges are snapped ------
# Calibrated on the 45 approved clips: 1.05 to 4.6 words/s, longest silence 9.2 s at most
# (Whisper misses words shouted over loud game audio, so the silence reads a bit long).
# Words per second inside the clip; steady talk is 2-3.
CLIP_MIN_WPS = 0.6
# Longest stretch without a word inside the clip, edges included. Longer than this, the viewer
# watches the game in silence and swipes away.
CLIP_MAX_SILENCE_S = 12.0

# --- transcript sent to the AI ----------------------------------------------------------------
# A gap this long between transcript lines gets a "[... N s sem fala ...]" marker, so the AI
# sees where pure-gameplay stretches are. Half of CLIP_MAX_SILENCE_S: the AI should see a
# pause long before it is a reason to drop the clip.
SILENCE_MARK_S = 6.0

# "[Music]", "[Música]", "[Aplausos]", "[gunshots]"... Square brackets in captions hold a sound
# description or a speaker label, never words someone said, in any language. Except YouTube's
# censored swear word "[ __ ]" (no letters inside): that one was said, and loudly.
_BRACKET_TAG = re.compile(r"\[[^\[\]]{0,60}\]")
CENSORED = "__"


def _drop_cue(tag: re.Match[str]) -> str:
    return " " if any(c.isalpha() for c in tag.group()) else tag.group()


# Parentheses can hold real words, so only known cues: "(risos)", "(music playing)".
_CUE_WORDS = (
    r"m[uú]sica|musique|musik|music|applause|aplausos|applaudissements|laughter|laughs|"
    r"laughing|risos|risadas?|risas|rires|cheering|silence|sil[eê]ncio|noise|ru[ií]do|"
    r"inaud[ií]vel|inaudible"
)
_PAREN_CUE = re.compile(rf"\(\s*(?:{_CUE_WORDS})\b[^()]{{0,30}}\)", re.IGNORECASE)
# Music notes wrap song lyrics (radio, soundtrack): "♪ la la la ♪" is sung, not said. A note
# with no partner opens a lyric that runs to the end of the line ("♪ la la la").
_NOTES = "♪♫♬♩🎵🎶"
_LYRICS = re.compile(rf"[{_NOTES}][^{_NOTES}]*[{_NOTES}]")
_OPEN_LYRICS = re.compile(rf"[{_NOTES}].*$")


def clean_text(text: str) -> str:
    """Caption text without non-speech cues; "" when nothing spoken is left."""
    text = _BRACKET_TAG.sub(_drop_cue, text)
    for pattern in (_PAREN_CUE, _LYRICS, _OPEN_LYRICS):
        text = pattern.sub(" ", text)
    return " ".join(text.split()) if word_count(text) else ""


def clean_segments(segments: Sequence[Segment]) -> list[Segment]:
    """Drops cue-only segments and strips cues inside the rest. Idempotent."""
    out: list[Segment] = []
    for seg in segments:
        text = clean_text(seg["text"])
        if text:
            out.append(Segment(start=seg["start"], end=seg["end"], text=text))
    return out


def word_count(text: str) -> int:
    """Tokens with at least one letter or digit, plus censored words (">>", "-" and "…" are
    not words)."""
    return sum(1 for t in text.split() if t == CENSORED or any(c.isalnum() for c in t))


@dataclass(frozen=True)
class Span:
    start: float
    end: float
    words: int


# transcript segments, Whisper words, or spans already counted (see `spans`)
Timed = Sequence[Segment] | Sequence[Word] | Sequence[Span]


def spans(items: Timed) -> list[Span]:
    """Timed word counts; speechless items left out. Convert once when measuring many windows."""
    out: list[Span] = []
    for item in items:
        if isinstance(item, Span):
            out.append(item)
            continue
        n = word_count(item["text"] if "text" in item else item["word"])
        if n:
            out.append(Span(float(item["start"]), max(float(item["start"]), float(item["end"])), n))
    return out


def _merged(items: Sequence[Span], lo: float, hi: float) -> list[tuple[float, float]]:
    """Speech intervals clipped to [lo, hi], overlaps merged, in time order."""
    out: list[tuple[float, float]] = []
    clipped = sorted(
        (max(s.start, lo), min(s.end, hi)) for s in items if s.end > lo and s.start < hi
    )
    for start, end in clipped:
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _total(items: Sequence[Span], duration: float | None) -> float:
    if duration:
        return duration
    return max((s.end for s in items), default=0.0)


def speech_coverage(items: Timed, duration: float | None) -> float:
    """Share (0..1) of the video covered by speech. Duration unknown: up to the last word."""
    timed = spans(items)
    total = _total(timed, duration)
    if total <= 0:
        return 0.0
    return min(1.0, sum(end - start for start, end in _merged(timed, 0.0, total)) / total)


def words_per_minute(items: Timed, duration: float | None) -> float:
    timed = spans(items)
    total = _total(timed, duration)
    return sum(s.words for s in timed) / (total / 60) if total > 0 else 0.0


def window_words_per_second(items: Timed, start: float, end: float) -> float:
    """Words spoken inside [start, end] per second. A segment that only partly overlaps the
    window counts the same share of its words."""
    if end <= start:
        return 0.0
    words = 0.0
    for s in spans(items):
        if s.end <= s.start:  # zero-length word: inside or not
            words += s.words if start <= s.start < end else 0
            continue
        overlap = min(s.end, end) - max(s.start, start)
        if overlap > 0:
            words += s.words * overlap / (s.end - s.start)
    return words / (end - start)


def longest_silence(items: Timed, start: float, end: float) -> float:
    """Longest stretch of [start, end] without speech, counting the edges of the window."""
    if end <= start:
        return 0.0
    longest, cursor = 0.0, start
    for lo, hi in _merged(spans(items), start, end):
        longest = max(longest, lo - cursor)
        cursor = hi
    return max(longest, end - cursor)


@dataclass(frozen=True)
class VideoSpeech:
    coverage: float
    wpm: float

    @property
    def narrated(self) -> bool:
        return self.coverage >= VIDEO_MIN_COVERAGE and self.wpm >= VIDEO_MIN_WPM


def video_speech(segments: Sequence[Segment], duration: float | None) -> VideoSpeech:
    return VideoSpeech(speech_coverage(segments, duration), words_per_minute(segments, duration))


@dataclass(frozen=True)
class ClipSpeech:
    wps: float
    longest_silence: float

    @property
    def narrated(self) -> bool:
        return self.wps >= CLIP_MIN_WPS and self.longest_silence <= CLIP_MAX_SILENCE_S


def clip_speech(items: Timed, start: float, end: float) -> ClipSpeech:
    timed = spans(items)
    return ClipSpeech(
        window_words_per_second(timed, start, end), longest_silence(timed, start, end)
    )
