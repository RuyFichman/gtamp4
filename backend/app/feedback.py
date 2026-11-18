"""What the editor taught us: rejection reasons and real approved/rejected clips, turned into
examples for the clip-picking prompt (pipeline/score.py), and each channel's approval record
for the Radar (pipeline/ranking.py, pipeline/triage.py)."""

from collections import Counter, defaultdict
from typing import Literal

from sqlmodel import Session, col, func, or_, select

from app.models import Clip, ClipStatus, SourceVideo
from app.pipeline.ranking import ChannelHistory, ChannelRecord, channel_key

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

# rejections that say nothing about the source channel: the cut was wrong, not the video
NOT_THE_CHANNEL = ("cut_mid",)

EXAMPLES_PER_SIDE = 4
EDGE_TOLERANCE_S = 0.5  # smaller moves are noise, not a correction
TREND_MIN_CLIPS = 3
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


def edge_moves(clip: Clip) -> tuple[float, float] | None:
    """(start moved, end moved) in seconds from the edges the app delivered; positive = later.
    None when the clip predates the record or the editor left both edges alone."""
    if clip.ai_start_s is None or clip.ai_end_s is None:
        return None
    moves = (clip.start_s - clip.ai_start_s, clip.end_s - clip.ai_end_s)
    if all(abs(m) < EDGE_TOLERANCE_S for m in moves):
        return None
    return moves


def _quoted(video: SourceVideo, start: float, end: float) -> str:
    words = excerpt(video, start, end)
    return f' Trecho: "{words}"' if words else ""


def adjustment_lines(clip: Clip, video: SourceVideo) -> list[str]:
    """What the editor changed on the edges, with the words that went out or came in."""
    moves = edge_moves(clip)
    if moves is None or clip.ai_start_s is None or clip.ai_end_s is None:
        return []
    start_move, end_move = moves
    out = []
    if start_move >= EDGE_TOLERANCE_S:
        out.append(
            f"começou {start_move:.0f} s cedo demais; o editor tirou do início."
            + _quoted(video, clip.ai_start_s, clip.start_s)
        )
    elif start_move <= -EDGE_TOLERANCE_S:
        out.append(
            f"começou {-start_move:.0f} s tarde demais; o editor incluiu antes."
            + _quoted(video, clip.start_s, clip.ai_start_s)
        )
    if end_move <= -EDGE_TOLERANCE_S:
        out.append(
            f"terminou {-end_move:.0f} s depois do ponto certo; o editor tirou do fim."
            + _quoted(video, clip.end_s, clip.ai_end_s)
        )
    elif end_move >= EDGE_TOLERANCE_S:
        out.append(
            f"terminou {end_move:.0f} s cedo demais; o editor incluiu depois."
            + _quoted(video, clip.ai_end_s, clip.end_s)
        )
    return [f"  ajuste do editor: a IA {text}" for text in out]


def _line(clip: Clip, video: SourceVideo) -> str:
    if clip.status == ClipStatus.REJECTED:
        verdict = "RECUSADO"
        if clip.reject_reason in REJECT_REASONS:
            label, meaning = REJECT_REASONS[clip.reject_reason]
            verdict += f" ({label.lower()}: {meaning})"
    else:
        verdict = "APROVADO E POSTADO" if clip.status == ClipStatus.POSTED else "APROVADO"
        if edge_moves(clip):
            verdict += " APÓS AJUSTE DO EDITOR"
    lines = [
        f"- {verdict} | nota que a IA deu: {clip.potential} | {clip.end_s - clip.start_s:.0f} s"
        f' | vídeo: "{video.title}"',
        f'  trecho: "{excerpt(video, clip.start_s, clip.end_s)}"',
    ]
    if clip.status != ClipStatus.REJECTED:
        lines += adjustment_lines(clip, video)
    return "\n".join(lines)


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
    rows = list(session.exec(query.order_by(*order).limit(limit * 5)).all())
    # approved clips whose edges the editor corrected teach more than untouched ones
    rows.sort(key=lambda row: edge_moves(row[0]) is None)  # stable: keeps the order above
    return rows[:limit]


def adjustment_trend(session: Session) -> str:
    """How often the editor moves each edge of approved clips ("" with too little data)."""
    clips = session.exec(
        select(Clip).where(
            col(Clip.status).in_([ClipStatus.APPROVED, ClipStatus.POSTED]),
            col(Clip.ai_start_s).is_not(None),
            col(Clip.ai_end_s).is_not(None),
        )
    ).all()
    if len(clips) < TREND_MIN_CLIPS:
        return ""
    labels = {
        (0, 1): "atrasou o começo",
        (0, -1): "adiantou o começo",
        (1, -1): "encurtou o fim",
        (1, 1): "esticou o fim",
    }
    moved: dict[tuple[int, int], list[float]] = defaultdict(list)
    for clip in clips:
        for side, move in enumerate(edge_moves(clip) or ()):
            if abs(move) >= EDGE_TOLERANCE_S:
                moved[(side, 1 if move > 0 else -1)].append(abs(move))
    if not moved:
        return f"Nos {len(clips)} cortes aprovados o editor não mexeu no começo nem no fim."
    parts = [
        f"{labels[key]} em {len(v)} (em média {sum(v) / len(v):.0f} s)"
        for key, v in sorted(moved.items(), key=lambda kv: -len(kv[1]))
    ]
    return f"Ajustes do editor nos {len(clips)} cortes aprovados: " + ", ".join(parts) + "."


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
    trend = adjustment_trend(session)
    if trend:
        lines.append(trend)
    return "\n".join(lines)


def channel_history(session: Session) -> ChannelHistory:
    """Approved (incl. posted) vs rejected clips per source channel, for the Radar."""
    rows = session.exec(
        select(SourceVideo.channel, Clip.status, func.count())
        .join(SourceVideo, col(Clip.source_video_id) == col(SourceVideo.id))
        .where(
            col(Clip.status).in_([ClipStatus.APPROVED, ClipStatus.POSTED, ClipStatus.REJECTED]),
            or_(
                col(Clip.reject_reason).is_(None),
                col(Clip.reject_reason).not_in(NOT_THE_CHANNEL),
            ),
        )
        .group_by(col(SourceVideo.channel), col(Clip.status))
    ).all()
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for channel, status, n in rows:
        counts[channel_key(channel)][status == ClipStatus.REJECTED] += n
    records = {k: ChannelRecord(approved=a, rejected=r) for k, (a, r) in counts.items() if k}
    approved = sum(r.approved for r in records.values())
    decided = sum(r.decided for r in records.values())
    return ChannelHistory(records, approved / decided if decided else None)
