import struct
import zlib
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app import frames
from app.jobs import queue
from app.jobs.handlers import RENDER_CLIP
from app.models import Clip, ClipStatus, FrameTemplate, Job, SourceVideo


def png(width: int, height: int, color_type: int = 6) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return frames.PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", b"") + chunk(b"IEND", b"")


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    frames.get_settings.cache_clear()
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    frames.get_settings.cache_clear()


def test_validate_png() -> None:
    assert frames.validate(png(1080, 1920)).has_alpha
    with pytest.raises(frames.FrameError, match="PNG válido"):
        frames.validate(b"GIF89a....")
    with pytest.raises(frames.FrameError, match="9:16"):
        frames.validate(png(1920, 1080))
    with pytest.raises(frames.FrameError, match="transparência"):
        frames.validate(png(1080, 1920, color_type=2))
    with pytest.raises(frames.FrameError, match="baixa"):
        frames.validate(png(270, 480))


def test_add_default_delete(session: Session, tmp_path: Path) -> None:
    first = frames.add_frame(session, "Neon VI", png(1080, 1920))
    second = frames.add_frame(session, "Outra", png(720, 1280))
    assert first.is_default and not second.is_default  # first upload becomes default
    assert Path(first.overlay_path).parent == tmp_path / "frames"
    assert frames.png_size(Path(second.overlay_path)) == (720, 1280)

    frames.set_default(session, second.id)
    session.refresh(first)
    assert not first.is_default
    frames.set_default(session, None)
    assert not any(f.is_default for f in session.exec(select(FrameTemplate)))

    path = Path(second.overlay_path)
    frames.delete_frame(session, second.id or 0)
    assert not path.exists()
    with pytest.raises(LookupError):
        frames.set_default(session, 999)


def test_rerender_live_skips_busy_and_decided(session: Session) -> None:
    v = SourceVideo(youtube_id="y", url="u")
    session.add(v)
    session.commit()
    clips = [
        Clip(source_video_id=v.id or 0, start_s=0, end_s=20, file_path="a.mp4"),
        Clip(source_video_id=v.id or 0, start_s=0, end_s=20, file_path="b.mp4",
             status=ClipStatus.APPROVED),
        Clip(source_video_id=v.id or 0, start_s=0, end_s=20, file_path="c.mp4",
             status=ClipStatus.POSTED),
    ]  # fmt: skip
    session.add_all(clips)
    session.commit()
    queue.enqueue(session, RENDER_CLIP, {"clip_id": clips[0].id, "start_s": 0, "end_s": 20})
    assert frames.rerender_live(session) == 1  # only the approved one
    jobs = session.exec(select(Job)).all()
    assert {j.payload["clip_id"] for j in jobs} == {clips[0].id, clips[1].id}
