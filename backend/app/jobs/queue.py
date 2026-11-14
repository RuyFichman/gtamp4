from typing import Any

from sqlmodel import Session, col, select

from app.models import Job, JobStatus, utcnow


def enqueue(session: Session, kind: str, payload: dict[str, Any] | None = None) -> Job:
    job = Job(kind=kind, payload=payload or {}, message="Na fila")
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def claim_next(session: Session) -> Job | None:
    job = session.exec(
        select(Job).where(Job.status == JobStatus.QUEUED).order_by(col(Job.id))
    ).first()
    if job is None:
        return None
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.updated_at = utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def requeue_interrupted(session: Session) -> int:
    """On startup, jobs left RUNNING by a crash/restart go back to the queue."""
    jobs = session.exec(select(Job).where(Job.status == JobStatus.RUNNING)).all()
    for job in jobs:
        job.status = JobStatus.QUEUED
        job.message = "Retomando após reinício"
        job.updated_at = utcnow()
        session.add(job)
    session.commit()
    return len(jobs)


def update(session: Session, job: Job, **fields: Any) -> None:
    for key, value in fields.items():
        setattr(job, key, value)
    job.updated_at = utcnow()
    session.add(job)
    session.commit()
