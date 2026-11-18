from datetime import UTC, datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from app import stats
from app.jobs import queue
from app.models import Account, Clip, ClipStatus, JobStatus, SourceVideo


def test_stats_counts_rates_days_and_accounts() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as s:
        video = SourceVideo(youtube_id="v", url="u")
        acc = Account(platform="tiktok", handle="a")
        s.add_all([video, acc])
        s.commit()

        def clip(status: ClipStatus, potential: int, **kw: object) -> Clip:
            return Clip(
                source_video_id=video.id or 0,
                start_s=0,
                end_s=20,
                status=status,
                potential=potential,
                **kw,
            )

        s.add_all(
            [
                clip(ClipStatus.PENDING_REVIEW, 50),
                clip(ClipStatus.APPROVED, 80),
                clip(ClipStatus.APPROVED, 70, archived=True),  # "Pré-lançamento" tab
                clip(ClipStatus.POSTED, 90, account_id=acc.id, posted_at=now),
                clip(ClipStatus.REJECTED, 40),
                clip(ClipStatus.REJECTED, 20, created_at=now - timedelta(days=3)),
                clip(ClipStatus.REJECTED, 10, created_at=now - timedelta(days=30)),  # outside chart
            ]
        )
        s.commit()
        failed = queue.enqueue(s, "x")
        queue.update(s, failed, status=JobStatus.FAILED)

        out = stats.compute(s, today=now.astimezone().date())

    assert out.clips.total == 7
    assert (out.clips.pending_review, out.clips.posted, out.clips.rejected) == (1, 1, 3)
    assert (out.clips.approved, out.clips.archived_approved) == (2, 1)
    assert out.clips.archived_pending_review == 0
    assert out.approval_rate == 0.5  # 3 kept of 6 reviewed (archived ones still count)
    assert out.avg_potential_kept == 80.0
    assert out.avg_potential_rejected == 23.3
    assert len(out.days) == stats.DAYS
    assert out.days[-1].generated == 5 and out.days[-1].posted == 1
    assert out.days[-4].generated == 1
    assert sum(d.generated for d in out.days) == 6
    assert out.accounts[0].posted == 1 and out.accounts[0].last_posted_at is not None
    assert out.jobs.failed == 1
    assert out.radar.enabled is False
