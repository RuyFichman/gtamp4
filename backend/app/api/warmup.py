from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import warmup
from app.db import get_session
from app.models import Account

router = APIRouter(prefix="/api/warmup", tags=["warmup"])
SessionDep = Annotated[Session, Depends(get_session)]


class CheckIn(BaseModel):
    task_key: str
    done: bool


def _account(session: Session, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Conta não encontrada.")
    return account


@router.get("")
def list_warmup(session: SessionDep) -> list[warmup.WarmupOut]:
    accounts = session.exec(select(Account).order_by(Account.platform, Account.handle)).all()
    return [warmup.state(session, a) for a in accounts]


@router.post("/{account_id}/start")
def start(account_id: int, session: SessionDep) -> warmup.WarmupOut:
    account = _account(session, account_id)
    warmup.start(session, account)
    return warmup.state(session, account)


@router.post("/{account_id}/stop")
def stop(account_id: int, session: SessionDep) -> warmup.WarmupOut:
    account = _account(session, account_id)
    warmup.stop(session, account)
    return warmup.state(session, account)


@router.post("/{account_id}/check")
def check(account_id: int, body: CheckIn, session: SessionDep) -> warmup.WarmupOut:
    account = _account(session, account_id)
    try:
        warmup.set_check(session, account, body.task_key, body.done)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return warmup.state(session, account)
