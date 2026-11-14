from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.api import clips
from app.api.clips import clean_hashtags
from app.db import get_session
from app.jobs import handlers, queue
from app.models import Clip, Job, SourceVideo


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    src = tmp_path / "abc.mp4"
    src.write_bytes(b"video")
    old = tmp_path / "abc_0-20.mp4"
    old.write_bytes(b"clip")
    with Session(engine) as s:
        video = SourceVideo(
            youtube_id="abc",
            url="https://youtu.be/abc",
            duration_s=300,
            file_path=str(src),
            transcript=[{"start": 0, "end": 4, "text": "oi"}],
        )
        s.add(video)
        s.commit()
        s.add(
            Clip(source_video_id=video.id or 0, start_s=0, end_s=20, title="t", file_path=str(old))
        )
        s.commit()
    return engine


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    def session_override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app = FastAPI()
    app.include_router(clips.router)
    app.dependency_overrides[get_session] = session_override
    yield TestClient(app)


def edit(**over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "title": "t",
        "description": "d",
        "hashtags": [],
        "start_s": 0,
        "end_s": 20,
    }
    return body | over


def test_studio_returns_transcript_and_original(client: TestClient) -> None:
    body = client.get("/api/clips/1/studio").json()
    assert body["source_video_url"] == "/api/media/videos/abc.mp4"
    assert body["transcript"][0]["text"] == "oi"
    assert body["render_job"] is None


def test_text_only_edit_saves_without_render(client: TestClient, engine: Engine) -> None:
    body = client.patch(
        "/api/clips/1", json=edit(title=" Novo ", hashtags=["#GTA6 gtavi", "gta6"])
    ).json()
    assert body["clip"]["title"] == "Novo"
    assert body["clip"]["hashtags"] == ["GTA6", "gtavi"]
    assert body["render_job"] is None
    with Session(engine) as s:
        assert s.exec(select(Job)).first() is None


def test_time_edit_enqueues_render_once(client: TestClient) -> None:
    body = client.patch("/api/clips/1", json=edit(start_s=2.5, end_s=30)).json()
    assert body["render_job"]["kind"] == handlers.RENDER_CLIP
    assert body["clip"]["rendering"] is True
    assert body["clip"]["start_s"] == 0  # unchanged until the render succeeds
    r = client.patch("/api/clips/1", json=edit(start_s=3, end_s=30))
    assert r.status_code == 409


@pytest.mark.parametrize(
    ("start", "end"),
    [(-1, 10), (10, 5), (0, 2), (0, 200), (290, 320)],
)
def test_invalid_times_are_rejected(client: TestClient, start: float, end: float) -> None:
    assert client.patch("/api/clips/1", json=edit(start_s=start, end_s=end)).status_code == 400


def test_empty_title_is_rejected(client: TestClient) -> None:
    assert client.patch("/api/clips/1", json=edit(title="  ")).status_code == 400


def test_render_job_updates_clip_and_removes_old_file(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        handlers, "studio_clip_path", lambda yid, cid, s, e: tmp_path / f"{yid}_{cid}_{s}-{e}.mp4"
    )

    def fake_render(src: Path, dst: Path, start: float, end: float, *_: object) -> Path:
        dst.write_bytes(b"new")
        return dst

    monkeypatch.setattr(handlers.cut, "render_clip", fake_render)
    with Session(engine) as s:
        old_path = Path(s.exec(select(Clip)).one().file_path or "")
        job = queue.enqueue(s, handlers.RENDER_CLIP, {"clip_id": 1, "start_s": 5.0, "end_s": 25.0})
        handlers.render_clip(s, job)
        clip = s.exec(select(Clip)).one()
        assert (clip.start_s, clip.end_s) == (5.0, 25.0)
        assert Path(clip.file_path or "").read_bytes() == b"new"
        assert not old_path.exists()

        # same times again (new frame): a new file, the one being watched is kept until swapped
        first = Path(clip.file_path or "")
        job = queue.enqueue(s, handlers.RENDER_CLIP, {"clip_id": 1, "start_s": 5.0, "end_s": 25.0})
        handlers.render_clip(s, job)
        clip = s.exec(select(Clip)).one()
        assert Path(clip.file_path or "").name == f"{first.stem}_v{job.id}.mp4"
        assert not first.exists()


def test_clean_hashtags() -> None:
    assert clean_hashtags(["#a, b", "A", " #c "]) == ["a", "b", "c"]


def test_framing_change_alone_queues_render(client: TestClient, engine: Engine) -> None:
    with Session(engine) as s:
        clip = s.exec(select(Clip)).one()
        start, end = clip.start_s, clip.end_s
    body = edit(start_s=start, end_s=end) | {"zoom": 2.0, "pan_x": -0.5}
    out = client.patch("/api/clips/1", json=body).json()
    assert out["render_job"] is not None
    with Session(engine) as s:
        job = s.exec(select(Job)).one()
        assert job.payload["zoom"] == 2.0 and job.payload["start_s"] == start
    assert client.patch("/api/clips/1", json=body | {"zoom": 5}).status_code == 422
