from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, func, select

from app.api.schemas import AccountIn, AccountOut
from app.db import get_session
from app.models import Account, Clip, ClipStatus

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
SessionDep = Annotated[Session, Depends(get_session)]


def _clean(body: AccountIn) -> AccountIn:
    handle = body.handle.strip().lstrip("@")
    if not handle:
        raise HTTPException(400, "Informe o @ da conta.")
    return body.model_copy(
        update={"handle": handle, "name": body.name.strip(), "notes": body.notes.strip()}
    )


@router.get("")
def list_accounts(session: SessionDep) -> list[AccountOut]:
    counts = dict(
        session.exec(
            select(Clip.account_id, func.count())
            .where(Clip.status == ClipStatus.POSTED, col(Clip.account_id).is_not(None))
            .group_by(Clip.account_id)
        ).all()
    )
    accounts = session.exec(select(Account).order_by(Account.platform, Account.handle)).all()
    return [AccountOut.of(a, counts.get(a.id, 0)) for a in accounts]


@router.post("", status_code=201)
def create_account(body: AccountIn, session: SessionDep) -> AccountOut:
    account = Account(**_clean(body).model_dump())
    session.add(account)
    session.commit()
    session.refresh(account)
    return AccountOut.of(account)


@router.put("/{account_id}")
def update_account(account_id: int, body: AccountIn, session: SessionDep) -> AccountOut:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Conta não encontrada.")
    account.sqlmodel_update(_clean(body).model_dump())
    session.add(account)
    session.commit()
    session.refresh(account)
    return AccountOut.of(account)


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, session: SessionDep) -> None:
    account = session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "Conta não encontrada.")
    # posted clips keep their history, just without the account link
    for clip in session.exec(select(Clip).where(Clip.account_id == account_id)).all():
        clip.account_id = None
        session.add(clip)
    session.delete(account)
    session.commit()
