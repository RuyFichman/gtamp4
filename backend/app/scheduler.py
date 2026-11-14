"""Background timer: enqueues Radar scans and view refreshes when they are due.

A single 1-minute tick reads the config from the DB, so interval changes made in the
Radar tab take effect without restarting anything. It only enqueues jobs; the worker
runs them. It never publishes anything (posting is always manual)."""

import logging
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session

from app.db import get_engine
from app.jobs import queue
from app.jobs.radar_jobs import RADAR_SCAN, REFRESH_VIEWS
from app.models import utcnow
from app.store import get_radar_config, get_time, set_time

log = logging.getLogger(__name__)

VIEWS_EVERY = timedelta(hours=3)


def tick() -> None:
    try:
        with Session(get_engine()) as session:
            now = utcnow()
            config = get_radar_config(session)
            last = get_time(session, "radar_last_scan_at")
            due = last is None or now - last >= timedelta(minutes=config.interval_minutes)
            if config.enabled and due and not queue.has_pending(session, RADAR_SCAN):
                set_time(session, "radar_last_scan_at", now)
                queue.enqueue(session, RADAR_SCAN)

            last_views = get_time(session, "views_last_refresh_at")
            if (last_views is None or now - last_views >= VIEWS_EVERY) and not queue.has_pending(
                session, REFRESH_VIEWS
            ):
                set_time(session, "views_last_refresh_at", now)
                queue.enqueue(session, REFRESH_VIEWS)
    except Exception:  # noqa: BLE001 - the timer must survive anything
        log.exception("scheduler tick failed")


def start() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(tick, "interval", minutes=1, id="tick", max_instances=1, coalesce=True)
    scheduler.start()
    return scheduler
