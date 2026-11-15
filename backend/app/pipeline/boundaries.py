"""Move clip start/end to the nearest natural break, so a clip never opens or closes mid-word.

The AI picks times from subtitle lines, which are coarse (rolling auto captions). Whisper's
word timings (the same ones the burned-in captions use) show where the gaps between words
are and where sentences end ("." "!" "?"). Each edge goes to the best break near it: a
sentence end beats a comma, a long pause beats a short one, and moving far costs. The cut
then sits inside the gap: a breath before the first word, a little air after the last.
"""

from app.pipeline.types import Word

PAD_S = 3.0  # transcribe this much around the AI's window so breaks outside it are visible
MAX_SHIFT_S = 2.0
LEAD_S = 0.1  # before the first word
TAIL_S = 0.25  # after the last word
FULL_GAP_S = 0.6  # a pause this long counts as a full break
DISTANCE_COST = 0.8  # a move of MAX_SHIFT_S costs this much (a sentence end is worth 1.0)


def _punct_bonus(word: str) -> float:
    word = word.strip().rstrip("\"')]»”")
    if word.endswith((".", "!", "?", "…")):
        return 1.0
    if word.endswith((",", ";", ":")):
        return 0.4
    return 0.0


Window = tuple[float, float]


def _with_edges(words: list[Word], window: Window | None) -> list[Word]:
    """Silence at the edges of the transcribed window is a break too (e.g. the first word of
    the video). Empty words: they count as a pause, never as a sentence end."""
    if window is None:
        return words
    lo, hi = window
    return [Word(start=lo, end=lo, word=""), *words, Word(start=hi, end=hi, word="")]


def best_break(
    words: list[Word], target: float, window: Window | None = None
) -> tuple[Word, Word] | None:
    """The pair of consecutive words (before, after) that makes the best cut near `target`."""
    best: tuple[float, tuple[Word, Word]] | None = None
    words = _with_edges(words, window)
    for prev, nxt in zip(words, words[1:], strict=False):
        # Whisper sometimes splits one word ("GT" + "-A6"): not a break
        if nxt["word"].startswith("-") or prev["word"].endswith("-"):
            continue
        distance = max(0.0, prev["end"] - target, target - nxt["start"])  # 0 inside the gap
        if distance > MAX_SHIFT_S:
            continue
        gap = max(0.0, nxt["start"] - prev["end"])
        score = (
            min(gap, FULL_GAP_S) / FULL_GAP_S
            + _punct_bonus(prev["word"])
            - DISTANCE_COST * distance / MAX_SHIFT_S
        )
        if best is None or score > best[0]:
            best = (score, (prev, nxt))
    return best[1] if best else None


def snap_start(words: list[Word], target: float, window: Window | None = None) -> float:
    pair = best_break(words, target, window)
    if pair is None:  # no speech around (music, silence): keep the AI's time
        return target
    prev, nxt = pair
    return round(max(prev["end"], nxt["start"] - LEAD_S), 2)


def snap_end(words: list[Word], target: float, window: Window | None = None) -> float:
    pair = best_break(words, target, window)
    if pair is None:
        return target
    prev, nxt = pair
    return round(min(nxt["start"], prev["end"] + TAIL_S), 2)


def snap_clip(
    words: list[Word],
    start: float,
    end: float,
    min_s: float,
    max_s: float,
    window: Window | None = None,
) -> tuple[float, float]:
    """Both edges snapped; falls back side by side if that breaks the length limits.
    `words` cover `window` (source seconds), ideally [start - PAD_S, end + PAD_S]."""
    new_start, new_end = snap_start(words, start, window), snap_end(words, end, window)
    for s, e in ((new_start, new_end), (start, new_end), (new_start, end)):
        if e > s and min_s <= e - s <= max_s:
            return s, e
    return start, end
