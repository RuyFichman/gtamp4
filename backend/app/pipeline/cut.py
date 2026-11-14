"""Render a 9:16 clip: blurred fill background, centered original, optional frame overlay."""

from pathlib import Path

from app.pipeline.encoder import SW_ENCODER, encoder_args, pick_encoder
from app.pipeline.proc import CommandError, run

W, H = 1080, 1920


def build_cut_command(
    src: Path, dst: Path, start: float, end: float, frame: Path | None, encoder: str
) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", str(src)]  # fmt: skip
    graph = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2[bgb];"
        f"[fg]scale={W}:-2[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2"
    )
    if frame is not None:
        cmd += ["-i", str(frame)]
        graph += f"[base];[1:v]scale={W}:{H}[fr];[base][fr]overlay=0:0"
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
) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    encoder = pick_encoder(encoder_choice)
    try:
        run(build_cut_command(src, dst, start, end, frame, encoder))
    except CommandError:
        if encoder == SW_ENCODER:
            raise
        run(build_cut_command(src, dst, start, end, frame, SW_ENCODER))  # AMF hiccup: CPU retry
    return dst
