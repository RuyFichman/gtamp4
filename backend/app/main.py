import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import app.jobs.handlers  # noqa: F401  (registers job handlers)
import app.jobs.radar_jobs  # noqa: F401
from app import scheduler
from app.api import accounts, clips, jobs, radar, settings, stats, system, videos
from app.config import get_settings
from app.db import init_db
from app.jobs.worker import Worker

logging.basicConfig(level=logging.INFO)

config = get_settings()
config.ensure_dirs()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    worker = Worker()
    worker.start()
    timer = scheduler.start()
    yield
    timer.shutdown(wait=False)
    worker.stop()


app = FastAPI(title="gtamp4", lifespan=lifespan)
for router in (
    system.router,
    videos.router,
    jobs.router,
    clips.router,
    accounts.router,
    radar.router,
    stats.router,
    settings.router,
):
    app.include_router(router)
app.mount("/api/media/clips", StaticFiles(directory=config.clips_dir), name="clips")
# originals, for the Studio player (StaticFiles serves byte ranges, so seeking works)
app.mount("/api/media/videos", StaticFiles(directory=config.videos_dir), name="videos")
