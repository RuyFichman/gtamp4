import logging
import threading
from collections.abc import Callable

from sqlmodel import Session

from app.db import get_engine
from app.jobs import queue
from app.models import Job, JobStatus

log = logging.getLogger(__name__)

Handler = Callable[[Session, Job], None]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return register


def process_one(session: Session) -> bool:
    """Run the next queued job. Returns False when the queue is empty."""
    job = queue.claim_next(session)
    if job is None:
        return False
    fn = HANDLERS.get(job.kind)
    try:
        if fn is None:
            raise RuntimeError(f"Tipo de job desconhecido: {job.kind}")
        fn(session, job)
        queue.update(session, job, status=JobStatus.DONE, progress=1.0, message="Concluído")
    except Exception as exc:  # noqa: BLE001 - every failure must land on the job
        log.exception("job %s failed", job.id)
        queue.update(session, job, status=JobStatus.FAILED, message="Falhou", error=str(exc))
    return True


class Worker:
    def __init__(self, idle_seconds: float = 2.0) -> None:
        self._stop = threading.Event()
        self._idle = idle_seconds
        self._thread = threading.Thread(target=self._loop, name="job-worker", daemon=True)

    def start(self) -> None:
        with Session(get_engine()) as session:
            n = queue.requeue_interrupted(session)
            if n:
                log.info("requeued %d interrupted job(s)", n)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            with Session(get_engine()) as session:
                worked = process_one(session)
            if not worked:
                self._stop.wait(self._idle)
