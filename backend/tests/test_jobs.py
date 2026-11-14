import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.jobs import queue
from app.jobs.worker import HANDLERS, process_one
from app.models import Job, JobStatus


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_job_runs_and_completes(session: Session) -> None:
    calls: list[int] = []
    HANDLERS["test_ok"] = lambda s, job: calls.append(job.id)
    job = queue.enqueue(session, "test_ok")

    assert process_one(session) is True
    session.refresh(job)
    assert job.status == JobStatus.DONE
    assert calls == [job.id]
    assert process_one(session) is False


def test_failure_is_recorded_on_job(session: Session) -> None:
    def boom(s: Session, job: Job) -> None:
        raise RuntimeError("ffmpeg saiu com código 1")

    HANDLERS["test_fail"] = boom
    job = queue.enqueue(session, "test_fail")
    process_one(session)
    session.refresh(job)
    assert job.status == JobStatus.FAILED
    assert "ffmpeg" in (job.error or "")


def test_interrupted_jobs_are_requeued(session: Session) -> None:
    job = queue.enqueue(session, "anything")
    queue.claim_next(session)
    assert queue.requeue_interrupted(session) == 1
    session.refresh(job)
    assert job.status == JobStatus.QUEUED
    assert job.message == "Retomando após reinício"


def test_known_youtube_errors_get_a_hint(session: Session) -> None:
    def blocked(s: Session, job: Job) -> None:
        raise RuntimeError("ERROR: [youtube] abc: Sign in to confirm you’re not a bot.")

    HANDLERS["test_bot"] = blocked
    job = queue.enqueue(session, "test_bot")
    process_one(session)
    session.refresh(job)
    assert (job.error or "").startswith("O YouTube pediu verificação")
    assert "not a bot" in (job.error or "")  # raw error kept below the hint
