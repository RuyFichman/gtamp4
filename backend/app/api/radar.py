from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.api.schemas import JobOut, _UtcModel
from app.db import get_session
from app.jobs import queue
from app.jobs.radar_jobs import RADAR_SCAN, send_candidate, sent_last_24h
from app.models import CandidateStatus, RadarCandidate, RadarQuery
from app.store import RadarConfig, get_radar_config, get_time, set_radar_config

router = APIRouter(prefix="/api/radar", tags=["radar"])
SessionDep = Annotated[Session, Depends(get_session)]


class RadarStatusOut(_UtcModel):
    config: RadarConfig
    last_scan_at: datetime | None
    next_scan_at: datetime | None
    sent_last_24h: int
    scanning: bool


class QueryIn(BaseModel):
    kind: Literal["search", "channel"]
    query: str


class QueryPatch(BaseModel):
    enabled: bool


class QueryOut(_UtcModel):
    id: int
    kind: str
    query: str
    enabled: bool
    last_run_at: datetime | None
    last_error: str | None


class CandidateOut(_UtcModel):
    id: int
    youtube_id: str
    url: str
    title: str
    channel: str
    duration_s: float | None
    views: int | None
    status: CandidateStatus
    reason: str
    found_at: datetime
    sent_at: datetime | None


def _status(session: Session) -> RadarStatusOut:
    config = get_radar_config(session)
    last = get_time(session, "radar_last_scan_at")
    nxt = None
    if config.enabled:
        nxt = last + timedelta(minutes=config.interval_minutes) if last else None
    return RadarStatusOut(
        config=config,
        last_scan_at=last,
        next_scan_at=nxt,
        sent_last_24h=sent_last_24h(session),
        scanning=queue.has_pending(session, RADAR_SCAN),
    )


@router.get("")
def get_status(session: SessionDep) -> RadarStatusOut:
    return _status(session)


@router.put("/config")
def put_config(body: RadarConfig, session: SessionDep) -> RadarStatusOut:
    set_radar_config(session, body)
    return _status(session)


@router.post("/scan", status_code=201)
def scan_now(session: SessionDep) -> JobOut:
    if queue.has_pending(session, RADAR_SCAN):
        raise HTTPException(409, "O Radar já está buscando. Aguarde terminar.")
    return JobOut.of(queue.enqueue(session, RADAR_SCAN))


def _query_out(q: RadarQuery) -> QueryOut:
    return QueryOut(
        id=q.id or 0,
        kind=q.kind,
        query=q.query,
        enabled=q.enabled,
        last_run_at=q.last_run_at,
        last_error=q.last_error,
    )


@router.get("/queries")
def list_queries(session: SessionDep) -> list[QueryOut]:
    rows = session.exec(select(RadarQuery).order_by(RadarQuery.kind, RadarQuery.id)).all()
    return [_query_out(q) for q in rows]


@router.post("/queries", status_code=201)
def add_query(body: QueryIn, session: SessionDep) -> QueryOut:
    text = body.query.strip()
    if not text:
        raise HTTPException(400, "Digite um termo de busca ou um canal.")
    q = RadarQuery(kind=body.kind, query=text)
    session.add(q)
    session.commit()
    session.refresh(q)
    return _query_out(q)


@router.patch("/queries/{query_id}")
def patch_query(query_id: int, body: QueryPatch, session: SessionDep) -> QueryOut:
    q = session.get(RadarQuery, query_id)
    if q is None:
        raise HTTPException(404, "Busca não encontrada.")
    q.enabled = body.enabled
    session.add(q)
    session.commit()
    session.refresh(q)
    return _query_out(q)


@router.delete("/queries/{query_id}", status_code=204)
def delete_query(query_id: int, session: SessionDep) -> None:
    q = session.get(RadarQuery, query_id)
    if q is None:
        raise HTTPException(404, "Busca não encontrada.")
    session.delete(q)
    session.commit()


@router.get("/candidates")
def list_candidates(session: SessionDep, limit: int = 80) -> list[CandidateOut]:
    rows = session.exec(
        select(RadarCandidate).order_by(col(RadarCandidate.id).desc()).limit(min(limit, 300))
    ).all()
    return [CandidateOut.model_validate(c, from_attributes=True) for c in rows]


@router.post("/candidates/{cand_id}/send")
def send_now(cand_id: int, session: SessionDep) -> CandidateOut:
    """Manual override: process this video now, ignoring triage and the daily quota."""
    cand = session.get(RadarCandidate, cand_id)
    if cand is None:
        raise HTTPException(404, "Vídeo não encontrado.")
    if cand.status == CandidateStatus.SENT:
        raise HTTPException(409, "Esse vídeo já foi enviado para corte.")
    send_candidate(session, cand)
    session.refresh(cand)
    return CandidateOut.model_validate(cand, from_attributes=True)
