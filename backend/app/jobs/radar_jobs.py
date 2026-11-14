"""Radar jobs: scan for new videos, and refresh view counts of source videos."""

import logging
from datetime import timedelta

from sqlmodel import Session, col, func, or_, select

from app.jobs import queue
from app.jobs.handlers import PROCESS_VIDEO
from app.jobs.worker import handler
from app.models import (
    CandidateStatus,
    Clip,
    ClipStatus,
    Job,
    JobStatus,
    RadarCandidate,
    RadarQuery,
    SourceVideo,
    utcnow,
)
from app.pipeline import download, radar, triage
from app.pipeline.radar import Found
from app.store import get_app_config, get_radar_config, set_time

log = logging.getLogger(__name__)

RADAR_SCAN = "radar_scan"
REFRESH_VIEWS = "refresh_views"
VIEWS_MAX_AGE = timedelta(hours=6)
VIEWS_WINDOW = timedelta(days=30)
VIEWS_PER_RUN = 20
WAITING_MAX_AGE = timedelta(days=3)


def sent_last_24h(session: Session) -> int:
    """Videos sent in the last 24 h; failed ones (deleted, blocked...) don't use the quota."""
    since = utcnow() - timedelta(hours=24)
    return session.exec(
        select(func.count())
        .select_from(RadarCandidate)
        .outerjoin(Job, col(Job.id) == col(RadarCandidate.job_id))
        .where(
            RadarCandidate.status == CandidateStatus.SENT,
            col(RadarCandidate.sent_at) >= since,
            or_(col(Job.id).is_(None), Job.status != JobStatus.FAILED),
        )
    ).one()


def send_candidate(session: Session, cand: RadarCandidate) -> None:
    job = queue.enqueue(session, PROCESS_VIDEO, {"url": cand.url, "title": cand.title})
    cand.status = CandidateStatus.SENT
    cand.job_id = job.id
    cand.sent_at = utcnow()
    session.add(cand)
    session.commit()


def _collect(session: Session, job: Job) -> tuple[list[tuple[Found, int]], list[str]]:
    """Run every enabled query; return unseen videos and per-query errors."""
    queries = session.exec(select(RadarQuery).where(RadarQuery.enabled)).all()
    if not queries:
        raise RuntimeError("Nenhum termo ou canal ativo no Radar. Cadastre um na aba Radar.")
    seen = set(session.exec(select(RadarCandidate.youtube_id)).all())
    seen |= set(session.exec(select(SourceVideo.youtube_id)).all())
    fresh: list[tuple[Found, int]] = []
    errors: list[str] = []
    for i, q in enumerate(queries):
        queue.update(
            session, job, progress=0.05 + 0.5 * i / len(queries), message=f"Buscando: {q.query}"
        )
        try:
            found = radar.list_videos(q.kind, q.query)
            q.last_error = None
        except Exception as exc:  # noqa: BLE001 - one bad query must not stop the others
            log.warning("radar query %s failed: %s", q.query, exc)
            q.last_error = str(exc)[-300:]
            errors.append(f"{q.query}: {q.last_error}")
            found = []
        q.last_run_at = utcnow()
        session.add(q)
        session.commit()
        for video in found:
            if video.youtube_id not in seen:
                seen.add(video.youtube_id)
                fresh.append((video, q.id or 0))
    if errors and len(errors) == len(queries):
        raise RuntimeError("Todas as buscas falharam:\n" + "\n".join(errors))
    return fresh, errors


@handler(RADAR_SCAN)
def radar_scan(session: Session, job: Job) -> None:
    queue.update(session, job, payload={**job.payload, "title": "Radar: buscando vídeos novos"})
    set_time(session, "radar_last_scan_at", utcnow())
    fresh, errors = _collect(session, job)

    to_triage: list[Found] = []
    for video, query_id in fresh:
        cand = RadarCandidate(
            youtube_id=video.youtube_id,
            url=video.url,
            title=video.title,
            channel=video.channel,
            duration_s=video.duration_s,
            views=video.views,
            query_id=query_id,
        )
        reason = radar.prefilter(video)
        if reason:
            cand.reason = reason
        else:
            cand.status = CandidateStatus.WAITING
            cand.reason = "Aguardando triagem"
            to_triage.append(video)
        session.add(cand)
    session.commit()

    if to_triage:
        queue.update(session, job, progress=0.6, message=f"Triagem de {len(to_triage)} vídeo(s)")
        recent = session.exec(
            select(RadarCandidate.title)
            .where(RadarCandidate.status == CandidateStatus.SENT)
            .order_by(col(RadarCandidate.sent_at).desc())
            .limit(30)
        ).all()
        model = get_app_config(session).model_triage
        decisions = triage.triage(to_triage, list(recent), model)
        for video in to_triage:
            cand = session.exec(
                select(RadarCandidate).where(RadarCandidate.youtube_id == video.youtube_id)
            ).one()
            decision = decisions.get(video.youtube_id)
            if decision is None:
                cand.status, cand.reason = CandidateStatus.REJECTED, "A triagem não avaliou"
            else:
                cand.status = CandidateStatus.WAITING if decision.keep else CandidateStatus.REJECTED
                cand.reason = decision.reason
            session.add(cand)
        session.commit()

    sent = dispatch(session)
    summary = f"{len(fresh)} novo(s), {len(to_triage)} na triagem, {sent} enviado(s) para corte"
    if errors:
        summary += f" · {len(errors)} busca(s) falharam"
    queue.update(session, job, payload={**job.payload, "title": f"Radar: {summary}"})


def expire_waiting(session: Session) -> None:
    """News goes stale: drop candidates that waited for quota longer than WAITING_MAX_AGE."""
    old = session.exec(
        select(RadarCandidate).where(
            RadarCandidate.status == CandidateStatus.WAITING,
            col(RadarCandidate.found_at) < utcnow() - WAITING_MAX_AGE,
        )
    ).all()
    for cand in old:
        cand.status = CandidateStatus.REJECTED
        cand.reason = "Ficou velho na espera (limite diário cheio)"
        session.add(cand)
    session.commit()


def dispatch(session: Session) -> int:
    """Send waiting candidates to processing, most viewed first, within the daily quota."""
    expire_waiting(session)
    quota = get_radar_config(session).daily_limit - sent_last_24h(session)
    if quota <= 0:
        return 0
    waiting = session.exec(
        select(RadarCandidate)
        .where(RadarCandidate.status == CandidateStatus.WAITING)
        .order_by(col(RadarCandidate.views).desc(), col(RadarCandidate.id).desc())
        .limit(quota)
    ).all()
    for cand in waiting:
        send_candidate(session, cand)
    return len(waiting)


@handler(REFRESH_VIEWS)
def refresh_views(session: Session, job: Job) -> None:
    """Refresh views of recent source videos that still have live clips."""
    queue.update(session, job, payload={**job.payload, "title": "Atualizando views"})
    stale = utcnow() - VIEWS_MAX_AGE
    videos = session.exec(
        select(SourceVideo)
        .where(
            col(SourceVideo.created_at) >= utcnow() - VIEWS_WINDOW,
            col(SourceVideo.id).in_(
                select(Clip.source_video_id).where(Clip.status != ClipStatus.REJECTED)
            ),
            (col(SourceVideo.views_checked_at).is_(None))
            | (col(SourceVideo.views_checked_at) < stale),
        )
        .order_by(col(SourceVideo.views_checked_at))
        .limit(VIEWS_PER_RUN)
    ).all()
    failed = 0
    for i, video in enumerate(videos):
        queue.update(session, job, progress=i / max(1, len(videos)), message=video.title[:60])
        try:
            video.views = download.fetch_views(video.url)
        except Exception as exc:  # noqa: BLE001 - deleted/private videos must not block others
            log.warning("views refresh failed for %s: %s", video.youtube_id, exc)
            failed += 1
            continue
        video.views_checked_at = utcnow()
        session.add(video)
        session.commit()
    title = f"Views atualizadas: {len(videos) - failed} vídeo(s)"
    if failed:
        title += f", {failed} falharam"
    queue.update(session, job, payload={**job.payload, "title": title})
