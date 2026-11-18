from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api import accounts, clips
from app.db import get_session
from app.models import Clip, ClipStatus, SourceVideo


@pytest.fixture
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        video = SourceVideo(youtube_id="abc", url="https://youtu.be/abc", title="v")
        s.add(video)
        s.commit()
        s.add(
            Clip(
                source_video_id=video.id or 0,
                start_s=0,
                end_s=20,
                title="t",
                status=ClipStatus.APPROVED,
            )
        )
        s.commit()

    def session_override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app = FastAPI()
    app.include_router(clips.router)
    app.include_router(accounts.router)
    app.dependency_overrides[get_session] = session_override
    yield TestClient(app)


def test_account_handle_is_cleaned(client: TestClient) -> None:
    r = client.post("/api/accounts", json={"platform": "tiktok", "handle": " @gta.cortes "})
    assert r.status_code == 201
    assert r.json()["handle"] == "gta.cortes"
    assert (
        client.post("/api/accounts", json={"platform": "tiktok", "handle": "@"}).status_code == 400
    )


def test_mark_posted_records_account_and_link(client: TestClient) -> None:
    acc = client.post("/api/accounts", json={"platform": "tiktok", "handle": "a"}).json()
    r = client.post(
        "/api/clips/1/status",
        json={"status": "posted", "account_id": acc["id"], "post_url": " https://tiktok.com/x "},
    )
    body = r.json()
    assert body["status"] == "posted"
    assert body["account_id"] == acc["id"]
    assert body["post_url"] == "https://tiktok.com/x"
    assert body["posted_at"] is not None
    assert client.get("/api/accounts").json()[0]["posted_count"] == 1

    # undo: back to the posting queue, post data cleared
    body = client.post("/api/clips/1/status", json={"status": "approved"}).json()
    assert body["account_id"] is None and body["posted_at"] is None


def test_unknown_account_is_rejected(client: TestClient) -> None:
    r = client.post("/api/clips/1/status", json={"status": "posted", "account_id": 99})
    assert r.status_code == 400


def test_deleting_account_keeps_posted_clip(client: TestClient) -> None:
    acc = client.post("/api/accounts", json={"platform": "instagram", "handle": "b"}).json()
    client.post("/api/clips/1/status", json={"status": "posted", "account_id": acc["id"]})
    assert client.delete(f"/api/accounts/{acc['id']}").status_code == 204
    posted = client.get("/api/clips?status=posted&sort=posted").json()
    assert len(posted) == 1 and posted[0]["account_id"] is None


def test_archive_moves_clip_out_of_the_queue_and_keeps_status(client: TestClient) -> None:
    assert [c["id"] for c in client.get("/api/clips?status=approved").json()] == [1]

    r = client.post("/api/clips/1/archive", json={"archived": True})
    assert r.status_code == 200
    assert r.json()["archived"] is True and r.json()["status"] == "approved"
    assert client.get("/api/clips?status=approved").json() == []
    shelf = client.get("/api/clips?status=approved&archived=true").json()
    assert [c["id"] for c in shelf] == [1]

    # status changes keep it on the shelf (approving/posting from the "Pré-lançamento" tab)
    client.post("/api/clips/1/status", json={"status": "posted"})
    assert client.get("/api/clips?status=posted&archived=true").json()[0]["id"] == 1

    client.post("/api/clips/1/archive", json={"archived": False})
    assert client.get("/api/clips?status=posted").json()[0]["archived"] is False
    assert client.post("/api/clips/99/archive", json={"archived": True}).status_code == 404
