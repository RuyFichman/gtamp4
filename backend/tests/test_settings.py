from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import maintenance
from app.api import settings
from app.db import get_session
from app.jobs import queue
from app.models import Clip, ClipStatus, SourceVideo
from app.store import get_app_config


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def client(engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "hw_encoder_works", lambda: False)

    def session_override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app = FastAPI()
    app.include_router(settings.router)
    app.dependency_overrides[get_session] = session_override
    yield TestClient(app)


def test_settings_roundtrip_and_validation(client: TestClient, engine) -> None:
    body = client.get("/api/settings").json()
    assert "anthropic_api_key" not in str(body).lower()
    cfg = body["config"] | {"min_clip_s": 20, "max_clip_s": 60, "max_clips": 3}
    assert client.put("/api/settings", json=cfg).status_code == 200
    with Session(engine) as s:
        assert get_app_config(s).max_clips == 3
    bad = cfg | {"min_clip_s": 60, "max_clip_s": 30}
    r = client.put("/api/settings", json=bad)
    assert r.status_code == 422
    assert "mínima" in str(r.json())


def test_cleanup_only_touches_decided_videos(engine, tmp_path: Path) -> None:
    done = tmp_path / "done.mp4"
    live = tmp_path / "live.mp4"
    done.write_bytes(b"x" * 10)
    live.write_bytes(b"y" * 5)
    with Session(engine) as s:
        v_done = SourceVideo(youtube_id="d", url="u", file_path=str(done))
        v_live = SourceVideo(youtube_id="l", url="u", file_path=str(live))
        s.add_all([v_done, v_live])
        s.commit()
        s.add_all(
            [
                Clip(source_video_id=v_done.id or 0, start_s=0, end_s=20, status=ClipStatus.POSTED),
                Clip(source_video_id=v_live.id or 0, start_s=0, end_s=20),  # pending
            ]
        )
        s.commit()
        assert maintenance.preview(s).bytes == 10

        job = queue.enqueue(s, "x")
        with pytest.raises(RuntimeError, match="fila"):
            maintenance.delete_originals(s)
        queue.update(s, job, status="done")

        assert maintenance.delete_originals(s).files == 1
        s.refresh(v_done)
        assert not done.exists() and live.exists() and v_done.file_path is None
