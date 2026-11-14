import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import system
from app.db import init_db
from app.jobs.worker import Worker

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    worker = Worker()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="gtamp4", lifespan=lifespan)
app.include_router(system.router)
