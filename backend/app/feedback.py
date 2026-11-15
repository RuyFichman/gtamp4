"""What the editor taught us: rejection reasons and real approved/rejected clips, turned into
examples for the clip-picking prompt (pipeline/score.py)."""

from collections import Counter
from typing import Literal

from sqlmodel import Session, col, func, select

from app.models import Clip, ClipStatus, SourceVideo

RejectReason = Literal["cut_mid", "no_context", "weak", "repeated", "off_topic", "bad_image"]

# key -> (button label in the UI, what it means, told to the AI)
REJECT_REASONS: dict[str, tuple[str, str]] = {
    "cut_mid": ("Cortou no meio", "começa ou termina no meio de uma frase ou ideia"),
    "no_context": ("Sem contexto", "não se entende sem ver o resto do vídeo"),
    "weak": ("Fraco / chato", "o trecho não tem nada que prenda a atenção"),
    "repeated": ("Assunto repetido", "assunto que já virou corte antes"),
    "off_topic": ("Não é GTA 6", "não é sobre GTA 6"),
    "bad_image": ("Imagem ruim", "o problema é a imagem do vídeo, não a escolha do trecho"),
}

EXAMPLES_PER_SIDE = 4
EXCERPT_HEAD = 220
EXCERPT_TAIL = 120


def excerpt(video: SourceVideo, start: float, end: float) -> str:
    """The clip's words from the stored transcript; beginning and end, since the hook and the
    ending are what the editor judges most."""
    words = " ".join(
        seg["text"]
        for seg in video.transcript or []
        if seg["end"] > start + 0.2 and seg["start"] < end - 0.2
    )
    if len(words) <= EXCERPT_HEAD + EXCERPT_TAIL + 5:
        return words
    return f"{words[:EXCERPT_HEAD].rstrip()} … {words[-EXCERPT_TAIL:].lstrip()}"


def _line(clip: Clip, video: SourceVideo) -> str:
    if clip.status == ClipStatus.REJECTED:
        verdict = "RECUSADO"
        if clip.reject_reason in REJECT_REASONS:
            label, meaning = REJECT_REASONS[clip.reject_reason]
            verdict += f" ({label.lower()}: {meaning})"
    else:
        verdict = "APROVADO E POSTADO" if clip.status == ClipStatus.POSTED else "APROVADO"
    return (
        f"- {verdict} | nota que a IA deu: {clip.potential} | {clip.end_s - clip.start_s:.0f} s"
        f' | vídeo: "{video.title}"\n'
        f'  trecho: "{excerpt(video, clip.start_s, clip.end_s)}"'
    )


def _recent(
    session: Session, statuses: list[ClipStatus], exclude_video_id: int | None, limit: int
) -> list[tuple[Clip, SourceVideo]]:
    query = (
        select(Clip, SourceVideo)
        .join(SourceVideo, col(Clip.source_video_id) == col(SourceVideo.id))
        .where(col(Clip.status).in_(statuses))
    )
    if exclude_video_id is not None:
        query = query.where(Clip.source_video_id != exclude_video_id)
    # rejections with a reason teach more than bare ones; then the most recent
    order = [col(Clip.reject_reason).is_(None), col(Clip.id).desc()]
    return list(session.exec(query.order_by(*order).limit(limit)).all())


def reason_counts(session: Session) -> Counter[str]:
    rows = session.exec(
        select(Clip.reject_reason, func.count())
        .where(Clip.status == ClipStatus.REJECTED, col(Clip.reject_reason).is_not(None))
        .group_by(col(Clip.reject_reason))
    ).all()
    return Counter({reason: n for reason, n in rows if reason in REJECT_REASONS})


def editor_examples(
    session: Session, exclude_video_id: int | None = None, per_side: int = EXAMPLES_PER_SIDE
) -> str:
    """Prompt block with recent decisions of the human editor ("" when there are none yet).
    Clips of the video being processed are left out so it does not grade its own clips."""
    good = _recent(session, [ClipStatus.APPROVED, ClipStatus.POSTED], exclude_video_id, per_side)
    bad = _recent(session, [ClipStatus.REJECTED], exclude_video_id, per_side)
    if not good and not bad:
        return ""
    lines = ["Decisões do editor (cortes reais que ele aprovou ou recusou):"]
    lines += [_line(c, v) for c, v in good + bad]
    counts = reason_counts(session)
    if counts:
        common = ", ".join(f"{REJECT_REASONS[k][0].lower()} ({n})" for k, n in counts.most_common())
        lines.append(f"Motivos de recusa mais comuns até agora: {common}.")
    return "\n".join(lines)
