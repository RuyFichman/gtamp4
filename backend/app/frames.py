"""Frame (moldura) templates: transparent 9:16 PNGs laid over every clip at render time.

The default frame is read by the render jobs; clips already rendered keep the frame they
were rendered with until re-rendered (see `rerender_live`)."""

import re
import secrets
import struct
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, col, select

from app.config import get_settings
from app.jobs import queue
from app.jobs.handlers import RENDER_CLIP, pending_renders
from app.models import Clip, ClipStatus, FrameTemplate

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 20 * 1024 * 1024
MIN_WIDTH = 540
LIVE = (ClipStatus.PENDING_REVIEW, ClipStatus.APPROVED)


class FrameError(ValueError):
    """Message is shown to the user (pt-BR)."""


@dataclass(frozen=True)
class PngInfo:
    width: int
    height: int
    has_alpha: bool


def inspect_png(data: bytes) -> PngInfo:
    if not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise FrameError("O arquivo não é um PNG válido.")
    width, height = struct.unpack(">II", data[16:24])
    color_type = data[25]
    has_alpha = color_type in (4, 6) or _has_chunk(data, b"tRNS")
    return PngInfo(width, height, has_alpha)


def _has_chunk(data: bytes, name: bytes) -> bool:
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        if kind == name:
            return True
        if kind in (b"IDAT", b"IEND"):
            return False  # tRNS must come before the image data
        pos += 12 + length
    return False


def validate(data: bytes) -> PngInfo:
    if len(data) > MAX_BYTES:
        raise FrameError("PNG grande demais (máx. 20 MB).")
    info = inspect_png(data)
    if abs(info.width / info.height - 9 / 16) > 0.01:
        raise FrameError(
            f"A moldura precisa ser vertical 9:16 (ex.: 1080x1920). Esta tem "
            f"{info.width}x{info.height}."
        )
    if info.width < MIN_WIDTH:
        raise FrameError(f"Resolução baixa demais ({info.width}px de largura; use 1080x1920).")
    if not info.has_alpha:
        raise FrameError(
            "O PNG não tem transparência: ele cobriria o vídeo inteiro. Exporte com fundo "
            "transparente na área do vídeo."
        )
    return info


def png_size(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as f:
            info = inspect_png(f.read(32))
    except (OSError, FrameError, struct.error):
        return None
    return info.width, info.height


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "moldura"


def add_frame(session: Session, name: str, data: bytes) -> FrameTemplate:
    name = name.strip()
    if not name:
        raise FrameError("Dê um nome para a moldura.")
    validate(data)
    frames_dir = get_settings().frames_dir
    frames_dir.mkdir(parents=True, exist_ok=True)
    path = frames_dir / f"{_slug(name)}_{secrets.token_hex(4)}.png"
    path.write_bytes(data)
    is_first = session.exec(select(FrameTemplate.id)).first() is None
    frame = FrameTemplate(name=name, overlay_path=str(path), is_default=is_first)
    session.add(frame)
    session.commit()
    session.refresh(frame)
    return frame


def set_default(session: Session, frame_id: int | None) -> None:
    """None = render without a frame."""
    if frame_id is not None and session.get(FrameTemplate, frame_id) is None:
        raise LookupError
    for frame in session.exec(select(FrameTemplate)).all():
        frame.is_default = frame.id == frame_id
        session.add(frame)
    session.commit()


def delete_frame(session: Session, frame_id: int) -> None:
    frame = session.get(FrameTemplate, frame_id)
    if frame is None:
        raise LookupError
    Path(frame.overlay_path).unlink(missing_ok=True)
    session.delete(frame)
    session.commit()


def live_clips(session: Session) -> list[Clip]:
    """Clips that can still be posted: worth re-rendering when the frame changes."""
    query = select(Clip).where(col(Clip.status).in_(LIVE), col(Clip.file_path).is_not(None))
    return list(session.exec(query).all())


def rerender_live(session: Session) -> int:
    busy = pending_renders(session)
    count = 0
    for clip in live_clips(session):
        if clip.id in busy:
            continue
        payload = {"clip_id": clip.id, "start_s": clip.start_s, "end_s": clip.end_s}
        queue.enqueue(session, RENDER_CLIP, payload)
        count += 1
    return count
