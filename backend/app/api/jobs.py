from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, or_, select

from app.api.schemas import JobOut
from app.db import get_session
from app.jobs import queue
from app.models import Job, JobStatus, utcnow

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("")
def list_jobs(session: SessionDep) -> list[JobOut]:
    """Active and failed jobs, plus ones finished in the last 2 minutes."""
    recent = utcnow() - timedelta(minutes=2)
    jobs = session.exec(
        select(Job)
        .where(
            or_(
                col(Job.status).in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.FAILED]),
                col(Job.updated_at) >= recent,
            )
        )
        .order_by(col(Job.id).desc())
        .limit(30)
    ).all()
    return [JobOut.of(j) for j in jobs]


@router.post("/{job_id}/retry")
def retry_job(job_id: int, session: SessionDep) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job não encontrado.")
    queue.update(session, job, status=JobStatus.QUEUED, error=None, progress=0, message="Na fila")
    return JobOut.of(job)


@router.delete("/{job_id}", status_code=204)
def dismiss_job(job_id: int, session: SessionDep) -> None:
    job = session.get(Job, job_id)
    if job is None or job.status == JobStatus.RUNNING:
        raise HTTPException(409, "Não dá para remover um job em andamento.")
    session.delete(job)
    session.commit()
