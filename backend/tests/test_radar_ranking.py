"""Radar picks by speed for the channel's size and by the channel's approval history."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import feedback
from app.api import radar as radar_api
from app.db import get_session
from app.jobs import queue, radar_jobs
from app.models import (
    CandidateStatus,
    Clip,
    ClipStatus,
    RadarCandidate,
    RadarChannel,
    RadarQuery,
    SourceVideo,
    utcnow,
)
from app.pipeline import radar, ranking, triage
from app.pipeline.radar import Found
from app.pipeline.ranking import ChannelHistory, ChannelRecord
from app.store import RadarConfig, set_radar_config

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


def add_clips(session: Session, channel: str, *statuses: ClipStatus, reason: str | None = None):
    video = SourceVideo(youtube_id=f"v{len(session.exec(select(SourceVideo)).all())}", url="u",
                        channel=channel)  # fmt: skip
    session.add(video)
    session.commit()
    for status in statuses:
        session.add(
            Clip(
                source_video_id=video.id or 0,
                start_s=0,
                end_s=20,
                status=status,
                reject_reason=reason if status == ClipStatus.REJECTED else None,
            )
        )
    session.commit()


# --- listing ------------------------------------------------------------------------------


def test_parse_entries_reads_publish_time_channel_and_subscribers() -> None:
    ts = NOW.timestamp()
    channel_page = {
        "channel": "Davy Jones GTA 6",
        "channel_id": "UCdavy",
        "channel_follower_count": 181000,
        "entries": [{"id": "a", "title": "T", "duration": 600, "view_count": 5, "timestamp": ts}],
    }
    [video] = radar.parse_entries(channel_page)
    assert video.published_at == NOW
    assert (video.channel_id, video.subscribers) == ("UCdavy", 181000)

    search_page = {"entries": [{"id": "b", "channel": "X", "channel_id": "UCx"}]}
    [video] = radar.parse_entries(search_page)
    assert video.published_at is None and video.subscribers is None
    assert video.channel_id == "UCx"


# --- score --------------------------------------------------------------------------------


def test_fast_video_on_small_channel_beats_slow_one_on_big_channel() -> None:
    hot = ranking.views_per_hour(50_000, NOW - timedelta(hours=6), NOW)
    slow = ranking.views_per_hour(200_000, NOW - timedelta(days=7), NOW)
    assert round(hot) == 8333 and round(slow) == 1190
    assert ranking.heat(hot, 20_000) > 10 * ranking.heat(slow, 2_000_000)


def test_tiny_channels_and_brand_new_videos_do_not_explode() -> None:
    # 500 views in 10 minutes on a 100-subscriber channel is not a hit
    tiny = ranking.heat(ranking.views_per_hour(500, NOW - timedelta(minutes=10), NOW), 100)
    solid = ranking.heat(ranking.views_per_hour(50_000, NOW - timedelta(hours=6), NOW), 20_000)
    assert tiny < solid / 10
    assert ranking.views_per_hour(None, None, NOW) == 0
    assert ranking.views_per_hour(4800, None, NOW) == 100  # unknown age: two days
    assert ranking.heat(1000, None) == ranking.heat(1000, ranking.SUBS_UNKNOWN)


def test_channel_weight_is_smoothed_and_clamped() -> None:
    assert ranking.channel_weight(None, 0.5) == 1
    assert ranking.channel_weight(ChannelRecord(8, 2), None) == 1  # nothing decided anywhere
    good = ranking.channel_weight(ChannelRecord(8, 2), 0.5)
    bad = ranking.channel_weight(ChannelRecord(1, 9), 0.5)
    one_miss = ranking.channel_weight(ChannelRecord(0, 1), 0.5)
    assert 1.5 < good <= ranking.WEIGHT_MAX
    assert bad == ranking.WEIGHT_MIN
    assert 0.6 < one_miss < 1  # a single rejection barely moves it
    assert ranking.is_bad_channel(ChannelRecord(1, 9))
    assert not ranking.is_bad_channel(ChannelRecord(0, 3))  # too few decisions to judge


# --- history ------------------------------------------------------------------------------


def test_channel_history_counts_decisions_per_channel(session: Session) -> None:
    add_clips(session, "Davy Jones GTA 6", ClipStatus.APPROVED, ClipStatus.POSTED,
              ClipStatus.REJECTED, ClipStatus.PENDING_REVIEW)  # fmt: skip
    add_clips(session, "Project Vice  ", ClipStatus.REJECTED, ClipStatus.REJECTED)
    # "cortou no meio" is the cut's fault, not the channel's
    add_clips(session, "project vice", ClipStatus.REJECTED, reason="cut_mid")
    history = feedback.channel_history(session)
    assert history.of("davy jones gta 6") == ChannelRecord(approved=2, rejected=1)
    assert history.of("Project  Vice") == ChannelRecord(approved=0, rejected=2)
    assert history.of("Nobody") is None
    assert history.overall_rate == pytest.approx(2 / 5)


def test_empty_history(session: Session) -> None:
    history = feedback.channel_history(session)
    assert history.records == {} and history.overall_rate is None


# --- dispatch order -----------------------------------------------------------------------


def waiting(vid: str, channel: str, speed: float | None, subs: int | None, views: int = 0):
    return RadarCandidate(
        youtube_id=vid,
        url="u",
        channel=channel,
        views=views,
        views_per_hour=speed,
        subscribers=subs,
        status=CandidateStatus.WAITING,
    )


def test_dispatch_sends_hottest_for_channel_size_then_history_tips_it(session: Session) -> None:
    set_radar_config(session, RadarConfig(enabled=True, interval_minutes=30, daily_limit=1))
    session.add_all(
        [
            # more views per hour, but on a channel 100x bigger
            waiting("big", "Grande", 30_000, 2_000_000, views=300_000),
            waiting("hot", "Pequeno", 8333, 20_000, views=50_000),
            waiting("old", "Antigo", None, None, views=200_000),  # no speed stored: views/48h
        ]
    )
    session.commit()
    order = [c.youtube_id for c in radar_jobs.waiting_queue(session)]
    assert order == ["hot", "big", "old"]

    # the editor keeps approving "Grande" and rejecting "Pequeno": history flips the order
    add_clips(session, "Grande", *[ClipStatus.APPROVED] * 10)
    add_clips(session, "Pequeno", *[ClipStatus.REJECTED] * 10)
    add_clips(session, "Outro", ClipStatus.APPROVED, ClipStatus.REJECTED)
    order = [c.youtube_id for c in radar_jobs.waiting_queue(session)]
    assert order.index("big") < order.index("hot")

    assert radar_jobs.dispatch(session) == 1
    sent = session.exec(
        select(RadarCandidate).where(RadarCandidate.status == CandidateStatus.SENT)
    ).one()
    assert sent.youtube_id == order[0]


# --- triage -------------------------------------------------------------------------------


def found(vid: str, channel: str, title: str = "GTA 6 vazou tudo") -> Found:
    return Found(vid, f"https://www.youtube.com/watch?v={vid}", title, channel, 600, 1000)


def test_heuristic_triage_drops_channels_the_editor_keeps_rejecting() -> None:
    history = ChannelHistory({"ruim": ChannelRecord(1, 9), "bom": ChannelRecord(5, 1)}, 0.5)
    out = triage.triage_heuristic([found("a", "Ruim"), found("b", "Bom"), found("c", "Novo")],
                                  history)  # fmt: skip
    assert not out["a"].keep and "1 de 10" in out["a"].reason
    assert out["b"].keep and out["c"].keep


def test_triage_prompt_shows_channel_history() -> None:
    history = ChannelHistory({"bom": ChannelRecord(5, 1)}, 0.5)
    line = triage._describe(found("b", "Bom"), history)
    assert "editor: 5 de 6 cortes aprovados" in line
    assert "editor:" not in triage._describe(found("c", "Novo"), history)
    assert "histórico do canal" in triage.SYSTEM_PROMPT


# --- scan ---------------------------------------------------------------------------------


def test_scan_stores_speed_and_caches_subscribers(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(RadarQuery(query="GTA 6"))
    session.commit()
    set_radar_config(session, RadarConfig(enabled=True, interval_minutes=30, daily_limit=0))
    published = utcnow() - timedelta(hours=10)

    def video(vid: str, channel_id: str, subs: int | None = None) -> Found:
        return Found(vid, "u", "GTA 6 news", f"Canal {channel_id}", 600, 20_000, channel_id,
                     published, subs)  # fmt: skip

    batches = iter(
        [
            [video("a", "UC1"), video("b", "UC1"), video("c", "UC2", subs=5_000)],
            [video("d", "UC1")],  # next scan: UC1 comes from the cache
        ]
    )
    monkeypatch.setattr(radar, "list_videos", lambda kind, q: next(batches))
    fetched: list[str] = []

    def subscribers(channel_id: str) -> int:
        fetched.append(channel_id)
        return 181_000

    monkeypatch.setattr(radar, "channel_subscribers", subscribers)
    monkeypatch.setattr(triage, "triage", lambda vs, *_: triage.triage_heuristic(vs))

    for _ in range(2):
        radar_jobs.radar_scan(session, queue.enqueue(session, radar_jobs.RADAR_SCAN))

    assert fetched == ["UC1"]  # once; UC2 came with the listing, then the cache served UC1
    by_id = {c.youtube_id: c for c in session.exec(select(RadarCandidate)).all()}
    assert by_id["a"].subscribers == by_id["d"].subscribers == 181_000
    assert by_id["c"].subscribers == 5_000
    assert by_id["a"].views_per_hour == pytest.approx(2000, rel=0.01)
    assert {c.channel_id for c in session.exec(select(RadarChannel)).all()} == {"UC1", "UC2"}


def test_failed_subscriber_lookup_does_not_stop_the_scan(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(RadarQuery(query="GTA 6"))
    session.commit()
    set_radar_config(session, RadarConfig(enabled=True, interval_minutes=30, daily_limit=0))
    monkeypatch.setattr(
        radar, "list_videos", lambda kind, q: [Found("a", "u", "GTA 6", "C", 600, 10, "UC9")]
    )

    def boom(channel_id: str) -> int:
        raise RuntimeError("HTTP 429")

    monkeypatch.setattr(radar, "channel_subscribers", boom)
    monkeypatch.setattr(triage, "triage", lambda vs, *_: triage.triage_heuristic(vs))
    radar_jobs.radar_scan(session, queue.enqueue(session, radar_jobs.RADAR_SCAN))
    cand = session.exec(select(RadarCandidate)).one()
    assert cand.status == CandidateStatus.WAITING and cand.subscribers is None
    assert session.exec(select(RadarChannel)).all() == []  # retried next scan


# --- API ----------------------------------------------------------------------------------


def test_candidates_api_shows_queue_position_and_channel_record(engine: Engine) -> None:
    with Session(engine) as s:
        s.add_all(
            [
                waiting("slow", "Grande", 100, 2_000_000),
                waiting("hot", "Pequeno", 8000, 20_000),
                RadarCandidate(youtube_id="sent", url="u", channel="Pequeno",
                               status=CandidateStatus.SENT),
            ]
        )  # fmt: skip
        s.commit()
        add_clips(s, "Pequeno", ClipStatus.APPROVED, ClipStatus.REJECTED, ClipStatus.APPROVED)

    def session_override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app = FastAPI()
    app.include_router(radar_api.router)
    app.dependency_overrides[get_session] = session_override
    rows = {r["youtube_id"]: r for r in TestClient(app).get("/api/radar/candidates").json()}
    assert rows["hot"]["queue_position"] == 1
    assert rows["slow"]["queue_position"] == 2
    assert rows["sent"]["queue_position"] is None
    assert rows["hot"]["channel_record"] == {"approved": 2, "decided": 3}
    assert rows["slow"]["channel_record"] is None
    assert rows["hot"]["views_per_hour"] == 8000
