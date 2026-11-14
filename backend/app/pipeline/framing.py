"""Suggest a Studio zoom for videos with black bars (e.g. phone footage inside a 16:9 frame).

ffmpeg `cropdetect` finds black borders only; blurred side bars are not detected."""

import re
from pathlib import Path

from app.pipeline.cut import MAX_ZOOM, Framing, H, W
from app.pipeline.proc import run

CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")
Box = tuple[int, int, int, int]  # width, height, x, y in source pixels


def probe_size(src: Path) -> tuple[int, int]:
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height", "-of", "csv=p=0", str(src)])  # fmt: skip
    width, height = out.stdout.strip().split(",")[:2]
    return int(width), int(height)


def detect_content(src: Path, start: float, end: float) -> Box | None:
    """Largest non-black area over (up to) 20 s of the clip."""
    out = run(["ffmpeg", "-hide_banner", "-ss", f"{start:.2f}", "-t", f"{min(end - start, 20):.2f}",
               "-i", str(src), "-vf", "fps=2,cropdetect=limit=24:round=2:reset=0",
               "-an", "-f", "null", "-"])  # fmt: skip
    boxes = CROP_RE.findall(out.stderr)
    if not boxes:
        return None
    w, h, x, y = (int(v) for v in boxes[-1])
    return w, h, x, y


def _pan(center: float, full: float, view: float) -> float:
    extra = full - view
    if extra <= 0:
        return 0.0
    return max(-1.0, min(1.0, (center - view / 2) / (extra / 2) - 1))


def suggest(src_w: int, src_h: int, box: Box) -> Framing | None:
    """Zoom so the content area fills the 9:16 frame as much as it can; None = no bars."""
    cw, ch, cx, cy = box
    if cw >= src_w * 0.9 and ch >= src_h * 0.9:
        return None
    zoom = min(src_w / cw, H * src_w / (W * ch), MAX_ZOOM)
    if zoom <= 1.05:
        return None
    scale = W * zoom / src_w  # output px per source px
    pan_x = _pan((cx + cw / 2) * scale, W * zoom, W)
    pan_y = _pan((cy + ch / 2) * scale, src_h * scale, H)
    return Framing(round(zoom, 2), round(pan_x, 3), round(pan_y, 3))
