from collections.abc import Iterator

import pytest
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine, select

from app.db import add_missing_columns
from app.jobs import queue, radar_jobs
from app.jobs.handlers import PROCESS_VIDEO
from app.models import CandidateStatus, Job, RadarCandidate, RadarQuery, SourceVideo
from app.pipeline import radar, triage
from app.pipeline.radar import Found
from app.store import RadarConfig, get_radar_config, set_radar_config


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def found(vid: str, title: str = "GTA 6 news", duration: float | None = 600, views: int = 100):
    return Found(vid, f"https://www.youtube.com/watch?v={vid}", title, "Canal", duration, views)


def test_channel_url_variants() -> None:
    assert radar.channel_url("@Rockstar") == "https://www.youtube.com/@Rockstar/videos"
    assert radar.channel_url("Rockstar") == "https://www.youtube.com/@Rockstar/videos"
    cid = "UC6VcWc1rAoWdBCM0JxrRQ3A"
    assert radar.channel_url(cid) == f"https://www.youtube.com/channel/{cid}/videos"
    assert radar.channel_url("https://www.youtube.com/@X/") == "https://www.youtube.com/@X/videos"
    assert "sp=CAI%3D" in radar.search_url("GTA 6")


def test_parse_entries_uses_playlist_channel() -> None:
    info = {
        "channel": "Rockstar Games",
        "entries": [
            {"id": "a", "title": "T", "duration": 30, "view_count": 5},
            {"id": "b", "ie_key": "YoutubeTab"},  # a nested playlist, not a video
            None,
        ],
    }
    out = radar.parse_entries(info)
    assert [f.youtube_id for f in out] == ["a"]
    assert out[0].channel == "Rockstar Games"


def test_prefilter() -> None:
    assert radar.prefilter(found("a", duration=None)) == "Ao vivo ou sem duração"
    assert "Curto" in (radar.prefilter(found("a", duration=40)) or "")
    assert "Longo" in (radar.prefilter(found("a", duration=4 * 3600)) or "")
    assert radar.prefilter(found("a")) is None


def test_heuristic_triage() -> None:
    out = triage.triage_heuristic([found("a", "GTA VI leak!"), found("b", "GTA 5 money glitch")])
    assert out["a"].keep and not out["b"].keep


def test_scan_dedupes_filters_and_respects_quota(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(RadarQuery(query="GTA 6"))
    session.add(SourceVideo(youtube_id="old", url="u"))
    session.commit()
    set_radar_config(session, RadarConfig(enabled=True, interval_minutes=30, daily_limit=2))

    videos = [
        found("old"),  # already processed manually
        found("short", duration=30),
        found("off", "Minecraft"),
        found("v1", views=10),
        found("v2", views=300),
        found("v3", views=200),
    ]
    monkeypatch.setattr(radar, "list_videos", lambda kind, q: videos)
    monkeypatch.setattr(triage, "triage", lambda vs, *_: triage.triage_heuristic(vs))

    job = queue.enqueue(session, radar_jobs.RADAR_SCAN)
    radar_jobs.radar_scan(session, job)

    by_id = {c.youtube_id: c for c in session.exec(select(RadarCandidate)).all()}
    assert "old" not in by_id
    assert by_id["short"].status == CandidateStatus.REJECTED
    assert by_id["off"].status == CandidateStatus.REJECTED
    # quota 2: the two fastest (same age and channel size: most viewed) go, the other waits
    assert by_id["v2"].status == CandidateStatus.SENT
    assert by_id["v3"].status == CandidateStatus.SENT
    assert by_id["v1"].status == CandidateStatus.WAITING
    jobs = session.exec(select(Job).where(Job.kind == PROCESS_VIDEO)).all()
    assert len(jobs) == 2

    # a second scan sees nothing new and the quota is used up
    radar_jobs.radar_scan(session, queue.enqueue(session, radar_jobs.RADAR_SCAN))
    assert len(session.exec(select(RadarCandidate)).all()) == len(by_id)
    assert len(session.exec(select(Job).where(Job.kind == PROCESS_VIDEO)).all()) == 2


def test_scan_without_queries_fails_clearly(session: Session) -> None:
    job = queue.enqueue(session, radar_jobs.RADAR_SCAN)
    with pytest.raises(RuntimeError, match="Nenhum termo"):
        radar_jobs.radar_scan(session, job)


def test_radar_config_defaults_and_roundtrip(session: Session) -> None:
    assert get_radar_config(session).enabled is False
    set_radar_config(session, RadarConfig(enabled=True, interval_minutes=60, daily_limit=5))
    assert get_radar_config(session).interval_minutes == 60


def test_add_missing_columns_upgrades_old_table() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE radarquery (id INTEGER PRIMARY KEY, query VARCHAR, enabled BOOLEAN)")
        )
        conn.execute(text("INSERT INTO radarquery (query, enabled) VALUES ('GTA 6', 1)"))
    SQLModel.metadata.create_all(engine)
    add_missing_columns(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("radarquery")}
    assert {"kind", "last_run_at", "last_error", "created_at"} <= cols
    with Session(engine) as s:
        assert s.exec(select(RadarQuery)).one().kind == "search"


def test_old_waiting_candidates_expire(session: Session) -> None:
    from datetime import timedelta

    from app.models import utcnow

    set_radar_config(session, RadarConfig(enabled=True, interval_minutes=30, daily_limit=0))
    old = RadarCandidate(
        youtube_id="x",
        url="u",
        status=CandidateStatus.WAITING,
        found_at=utcnow() - timedelta(days=4),
    )
    fresh = RadarCandidate(youtube_id="y", url="u", status=CandidateStatus.WAITING)
    session.add_all([old, fresh])
    session.commit()
    assert radar_jobs.dispatch(session) == 0
    session.refresh(old)
    session.refresh(fresh)
    assert old.status == CandidateStatus.REJECTED
    assert fresh.status == CandidateStatus.WAITING


def test_failed_sends_do_not_use_the_quota(session: Session) -> None:
    from app.models import JobStatus, utcnow

    ok = queue.enqueue(session, PROCESS_VIDEO)
    bad = queue.enqueue(session, PROCESS_VIDEO)
    queue.update(session, bad, status=JobStatus.FAILED)
    for vid, job in (("a", ok), ("b", bad)):
        session.add(
            RadarCandidate(
                youtube_id=vid,
                url="u",
                status=CandidateStatus.SENT,
                job_id=job.id,
                sent_at=utcnow(),
            )
        )
    session.commit()
    assert radar_jobs.sent_last_24h(session) == 1
