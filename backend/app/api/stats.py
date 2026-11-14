from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import stats
from app.db import get_session

router = APIRouter(prefix="/api/stats", tags=["stats"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("")
def get_stats(session: SessionDep) -> stats.Stats:
    return stats.compute(session)
