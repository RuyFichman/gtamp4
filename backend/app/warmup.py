"""Manual warm-up checklist for new TikTok/Instagram accounts.

The app only records what the user ticked. It NEVER automates likes, scrolling or posting
(that breaks the platforms' terms and gets accounts banned). The plan below is a common-sense
suggestion, not an official rule from TikTok or Instagram."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from pydantic import BaseModel
from sqlmodel import Session, select

from app.models import Account, WarmupCheck

TOTAL_DAYS = 14


@dataclass(frozen=True)
class Task:
    key: str
    text: str
    once: bool = False  # done once for the whole warm-up, not every day


@dataclass(frozen=True)
class Phase:
    first_day: int
    last_day: int
    title: str
    tip: str
    tasks: tuple[Task, ...]


PHASES = (
    Phase(
        1,
        3,
        "Só consumir",
        "Deixe o algoritmo entender o nicho antes de postar qualquer coisa.",
        (
            Task("profile", "Perfil completo: foto, nome e bio sobre GTA 6", once=True),
            Task("follow", "Seguir 5 a 10 contas grandes de GTA", once=True),
            Task("watch", "Assistir 20–30 min de vídeos de GTA no Para Você, até o fim"),
            Task("engage", "Curtir e comentar alguns vídeos do nicho, do seu jeito"),
            Task("no_post", "Não postar nada ainda"),
        ),
    ),
    Phase(
        4,
        7,
        "Começar devagar",
        "Se o Para Você já mostra quase só GTA, a conta está pronta para o primeiro post.",
        (
            Task("browse", "Navegar 15–20 min no nicho antes de postar"),
            Task("post_one", "Postar 1 corte (o de maior potencial)"),
            Task("reply", "Responder os comentários do dia"),
        ),
    ),
    Phase(
        8,
        TOTAL_DAYS,
        "Pegar ritmo",
        "Varie os horários e veja no Painel quais cortes você mais aprova.",
        (
            Task("post_two", "Postar 1–2 cortes em horários diferentes"),
            Task("browse_short", "Navegar 10–15 min no nicho"),
            Task("reply_fast", "Responder comentários na primeira hora após postar"),
        ),
    ),
)

ALL_KEYS = {t.key for p in PHASES for t in p.tasks}


def today() -> date:
    return datetime.now().astimezone().date()  # the user's local day


def phase_for(day_number: int) -> Phase | None:
    return next((p for p in PHASES if p.first_day <= day_number <= p.last_day), None)


class TaskOut(BaseModel):
    key: str
    text: str
    once: bool
    done: bool


class DayOut(BaseModel):
    date: date
    day_number: int
    done: int
    total: int


class WarmupOut(BaseModel):
    account_id: int
    handle: str
    platform: str
    started_on: date | None
    day_number: int | None  # 1..; > TOTAL_DAYS means finished
    finished: bool
    phase_title: str | None
    phase_tip: str | None
    tasks: list[TaskOut]
    days: list[DayOut]  # from start until today (max TOTAL_DAYS)


def _checks(session: Session, account_id: int) -> list[WarmupCheck]:
    return list(session.exec(select(WarmupCheck).where(WarmupCheck.account_id == account_id)))


def _daily_total(day_number: int) -> int:
    phase = phase_for(day_number)
    return len([t for t in phase.tasks if not t.once]) if phase else 0


def state(session: Session, account: Account, on: date | None = None) -> WarmupOut:
    on = on or today()
    base = WarmupOut(
        account_id=account.id or 0,
        handle=account.handle,
        platform=account.platform,
        started_on=account.warmup_started_on,
        day_number=None,
        finished=False,
        phase_title=None,
        phase_tip=None,
        tasks=[],
        days=[],
    )
    start = account.warmup_started_on
    if start is None:
        return base
    day_number = (on - start).days + 1
    checks = _checks(session, account.id or 0)
    once_done = {c.task_key for c in checks}
    today_done = {c.task_key for c in checks if c.day == on}
    phase = phase_for(day_number)
    tasks = [
        TaskOut(
            key=t.key,
            text=t.text,
            once=t.once,
            done=(t.key in once_done) if t.once else (t.key in today_done),
        )
        for t in (phase.tasks if phase else ())
    ]
    days = []
    for n in range(1, min(day_number, TOTAL_DAYS) + 1):
        d = start + timedelta(days=n - 1)
        p = phase_for(n)
        daily_keys = {t.key for t in p.tasks if not t.once} if p else set()
        done = len({c.task_key for c in checks if c.day == d} & daily_keys)
        days.append(DayOut(date=d, day_number=n, done=done, total=_daily_total(n)))
    return base.model_copy(
        update={
            "day_number": day_number,
            "finished": day_number > TOTAL_DAYS,
            "phase_title": phase.title if phase else None,
            "phase_tip": phase.tip if phase else None,
            "tasks": tasks,
            "days": days,
        }
    )


def start(session: Session, account: Account) -> None:
    for check in _checks(session, account.id or 0):
        session.delete(check)
    account.warmup_started_on = today()
    session.add(account)
    session.commit()


def stop(session: Session, account: Account) -> None:
    for check in _checks(session, account.id or 0):
        session.delete(check)
    account.warmup_started_on = None
    session.add(account)
    session.commit()


def set_check(session: Session, account: Account, key: str, done: bool) -> None:
    if key not in ALL_KEYS:
        raise ValueError("Tarefa desconhecida.")
    on = today()
    existing = session.exec(
        select(WarmupCheck).where(
            WarmupCheck.account_id == account.id,
            WarmupCheck.day == on,
            WarmupCheck.task_key == key,
        )
    ).first()
    if done and existing is None:
        session.add(WarmupCheck(account_id=account.id or 0, day=on, task_key=key))
    elif not done:
        # once-tasks may have been ticked on an earlier day: untick wherever it is
        q = select(WarmupCheck).where(
            WarmupCheck.account_id == account.id, WarmupCheck.task_key == key
        )
        for check in session.exec(q).all():
            session.delete(check)
    session.commit()
