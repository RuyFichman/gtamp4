from datetime import timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import warmup
from app.models import Account


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def make_account(session: Session) -> Account:
    a = Account(platform="tiktok", handle="nova")
    session.add(a)
    session.commit()
    return a


def test_not_started(session: Session) -> None:
    out = warmup.state(session, make_account(session))
    assert out.started_on is None and out.tasks == []


def test_start_and_tick_today(session: Session) -> None:
    a = make_account(session)
    warmup.start(session, a)
    out = warmup.state(session, a)
    assert out.day_number == 1 and out.phase_title == "Só consumir"
    warmup.set_check(session, a, "watch", True)
    warmup.set_check(session, a, "watch", True)  # idempotent
    out = warmup.state(session, a)
    assert [t.key for t in out.tasks if t.done] == ["watch"]
    assert out.days[0].done == 1 and out.days[0].total == 3  # once-tasks don't count per day
    warmup.set_check(session, a, "watch", False)
    assert not any(t.done for t in warmup.state(session, a).tasks)


def test_once_tasks_stay_done_and_phases_advance(session: Session) -> None:
    a = make_account(session)
    warmup.start(session, a)
    warmup.set_check(session, a, "profile", True)
    start = a.warmup_started_on
    assert start is not None
    later = warmup.state(session, a, on=start + timedelta(days=2))  # day 3
    assert next(t for t in later.tasks if t.key == "profile").done
    assert warmup.state(session, a, on=start + timedelta(days=4)).phase_title == "Começar devagar"
    done = warmup.state(session, a, on=start + timedelta(days=20))
    assert done.finished and done.tasks == [] and len(done.days) == warmup.TOTAL_DAYS


def test_unknown_task_and_stop(session: Session) -> None:
    a = make_account(session)
    warmup.start(session, a)
    with pytest.raises(ValueError):
        warmup.set_check(session, a, "bot_like", True)
    warmup.set_check(session, a, "watch", True)
    warmup.stop(session, a)
    assert warmup.state(session, a).started_on is None
