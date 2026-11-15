"""Render a 9:16 clip: blurred fill background, centered original, optional frame overlay,
optional burned-in captions (.ass, on top of everything)."""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.pipeline.encoder import SW_ENCODER, encoder_args, pick_encoder
from app.pipeline.proc import CommandError, run

W, H = 1080, 1920
MAX_ZOOM = 3.0


@dataclass(frozen=True)
class Framing:
    """Zoom of the centered video; pan -1..1 picks which part stays visible (0 = center)."""

    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0


def foreground_filter(f: Framing) -> str:
    if f.zoom <= 1.001:
        return f"scale={W}:-2"
    width = 2 * round(W * min(f.zoom, MAX_ZOOM) / 2)
    return (
        f"scale={width}:-2,"
        f"crop=w='min(iw,{W})':h='min(ih,{H})'"
        f":x='(iw-ow)/2*{1 + f.pan_x:.4f}':y='(ih-oh)/2*{1 + f.pan_y:.4f}'"
    )


def build_cut_command(
    src: Path,
    dst: Path,
    start: float,
    end: float,
    frame: Path | None,
    encoder: str,
    framing: Framing = Framing(),
    subtitles: str | None = None,
) -> list[str]:
    """`subtitles`: .ass file name relative to ffmpeg's working directory (a bare name avoids
    escaping Windows drive colons inside the filter graph)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", str(src)]  # fmt: skip
    graph = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2[bgb];"
        f"[fg]{foreground_filter(framing)}[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2"
    )
    if frame is not None:
        cmd += ["-i", str(frame)]
        graph += f"[base];[1:v]scale={W}:{H}[fr];[base][fr]overlay=0:0"
    if subtitles is not None:
        graph += f",ass={subtitles}"
    graph += ",format=yuv420p[v]"
    cmd += [
        "-filter_complex", graph,
        "-map", "[v]", "-map", "0:a?",
        *encoder_args(encoder),
        "-r", "30",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart",
        str(dst),
    ]  # fmt: skip
    return cmd


def render_clip(
    src: Path,
    dst: Path,
    start: float,
    end: float,
    frame: Path | None,
    encoder_choice: str = "auto",
    framing: Framing = Framing(),
    ass: str | None = None,
) -> Path:
    """`ass`: content of a caption file to burn in (see pipeline/captions.build_ass)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    encoder = pick_encoder(encoder_choice)
    with tempfile.TemporaryDirectory() as tmp:
        subs = None
        if ass is not None:
            subs = "captions.ass"
            (Path(tmp) / subs).write_text(ass, encoding="utf-8")
        # ffmpeg runs inside tmp: every other path must be absolute
        args = (src.resolve(), dst.resolve(), start, end, frame.resolve() if frame else None)
        try:
            run(build_cut_command(*args, encoder, framing, subs), cwd=Path(tmp))
        except CommandError:
            if encoder == SW_ENCODER:
                raise
            # AMF hiccup: CPU retry
            run(build_cut_command(*args, SW_ENCODER, framing, subs), cwd=Path(tmp))
    return dst
