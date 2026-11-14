import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import app.jobs.handlers  # noqa: F401  (registers job handlers)
from app.api import accounts, clips, jobs, system, videos
from app.config import get_settings
from app.db import init_db
from app.jobs.worker import Worker

logging.basicConfig(level=logging.INFO)

settings = get_settings()
settings.ensure_dirs()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    worker = Worker()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="gtamp4", lifespan=lifespan)
for router in (system.router, videos.router, jobs.router, clips.router, accounts.router):
    app.include_router(router)
app.mount("/api/media/clips", StaticFiles(directory=settings.clips_dir), name="clips")
