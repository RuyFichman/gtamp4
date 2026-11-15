import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, col, select

from app.api.schemas import (
    AutoFrameOut,
    ClipEditIn,
    ClipOut,
    ClipStatusIn,
    JobOut,
    Segment,
    StudioOut,
)
from app.db import get_session
from app.jobs import queue
from app.jobs.handlers import (
    RENDER_CLIP,
    STUDIO_MAX_S,
    STUDIO_MIN_S,
    pending_renders,
)
from app.models import Account, Clip, ClipStatus, FrameTemplate, SourceVideo, utcnow
from app.pipeline import framing as framing_detect
from app.pipeline.cut import Framing
from app.pipeline.proc import CommandError
from app.store import get_caption_style

router = APIRouter(prefix="/api/clips", tags=["clips"])
SessionDep = Annotated[Session, Depends(get_session)]

SORTS = {
    "potential": col(Clip.potential).desc(),
    "recent": col(Clip.id).desc(),
    "views": col(SourceVideo.views).desc(),
    "posted": col(Clip.posted_at).desc(),
}


@router.get("")
def list_clips(
    session: SessionDep,
    status: ClipStatus = ClipStatus.PENDING_REVIEW,
    sort: Literal["potential", "recent", "views", "posted"] = "potential",
) -> list[ClipOut]:
    rows = session.exec(
        select(Clip, SourceVideo)
        .join(SourceVideo, col(Clip.source_video_id) == col(SourceVideo.id))
        .where(Clip.status == status)
        .order_by(SORTS[sort], col(Clip.id).desc())
    ).all()
    rendering = pending_renders(session)
    return [ClipOut.of(c, v, rendering=c.id in rendering) for c, v in rows]


@router.post("/{clip_id}/status")
def set_status(clip_id: int, body: ClipStatusIn, session: SessionDep) -> ClipOut:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Corte não encontrado.")
    if body.status == ClipStatus.POSTED:
        if body.account_id is not None and session.get(Account, body.account_id) is None:
            raise HTTPException(400, "Conta não encontrada. Atualize a página e escolha de novo.")
        clip.account_id = body.account_id
        clip.post_url = (body.post_url or "").strip() or None
        clip.posted_at = utcnow()
    else:
        clip.account_id = None
        clip.post_url = None
        clip.posted_at = None
    clip.status = body.status
    session.add(clip)
    session.commit()
    session.refresh(clip)
    video = session.get(SourceVideo, clip.source_video_id)
    assert video is not None
    return ClipOut.of(clip, video)


@router.get("/{clip_id}/download")
def download_clip(clip_id: int, session: SessionDep) -> FileResponse:
    clip = session.get(Clip, clip_id)
    if clip is None or not clip.file_path or not Path(clip.file_path).exists():
        raise HTTPException(404, "Arquivo do corte não encontrado.")
    slug = re.sub(r"[^\w\- ]+", "", clip.title).strip()[:60] or f"corte-{clip.id}"
    return FileResponse(clip.file_path, media_type="video/mp4", filename=f"{slug}.mp4")


def _load(session: Session, clip_id: int) -> tuple[Clip, SourceVideo]:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Corte não encontrado.")
    video = session.get(SourceVideo, clip.source_video_id)
    if video is None:
        raise HTTPException(404, "Vídeo original não encontrado.")
    return clip, video


def _studio(session: Session, clip: Clip, video: SourceVideo) -> StudioOut:
    job = pending_renders(session).get(clip.id or 0)
    has_file = bool(video.file_path) and Path(video.file_path or "").exists()
    return StudioOut(
        clip=ClipOut.of(clip, video, rendering=job is not None),
        source_video_url=f"/api/media/videos/{Path(video.file_path or '').name}"
        if has_file
        else None,
        duration_s=video.duration_s,
        transcript=[Segment(**seg) for seg in video.transcript or []],
        render_job=JobOut.of(job) if job else None,
        min_s=STUDIO_MIN_S,
        max_s=STUDIO_MAX_S,
        frame_url=_frame_url(session),
        caption_style=get_caption_style(session),
    )


def _frame_url(session: Session) -> str | None:
    frame = session.exec(select(FrameTemplate).where(FrameTemplate.is_default)).first()
    return f"/api/media/frames/{Path(frame.overlay_path).name}" if frame else None


@router.get("/{clip_id}/studio")
def get_studio(clip_id: int, session: SessionDep) -> StudioOut:
    clip, video = _load(session, clip_id)
    return _studio(session, clip, video)


def clean_hashtags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for raw in tags:
        for tag in re.split(r"[\s,]+", raw):
            tag = tag.strip().lstrip("#")
            if tag and tag.lower() not in {t.lower() for t in out}:
                out.append(tag)
    return out


@router.patch("/{clip_id}")
def edit_clip(clip_id: int, body: ClipEditIn, session: SessionDep) -> StudioOut:
    """Save text right away; new start/end go to a render job (clip changes after it)."""
    clip, video = _load(session, clip_id)
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "O título não pode ficar vazio.")

    start, end = round(body.start_s, 2), round(body.end_s, 2)
    times_changed = abs(start - clip.start_s) > 0.05 or abs(end - clip.end_s) > 0.05
    framing = Framing(round(body.zoom, 2), round(body.pan_x, 3), round(body.pan_y, 3))
    framing_changed = framing != Framing(clip.zoom, clip.pan_x, clip.pan_y)
    captions = clip.captions if body.captions is None else body.captions
    captions_changed = captions != clip.captions
    if times_changed:
        limit = video.duration_s or float("inf")
        if start < 0 or end > limit + 0.5 or end <= start:
            raise HTTPException(
                400, "Início e fim precisam estar dentro do vídeo, com o fim depois do início."
            )
        if not STUDIO_MIN_S <= end - start <= STUDIO_MAX_S:
            raise HTTPException(
                400, f"O corte precisa ter entre {STUDIO_MIN_S:.0f} e {STUDIO_MAX_S:.0f} segundos."
            )
    needs_render = times_changed or framing_changed or captions_changed
    if needs_render and clip.id in pending_renders(session):
        raise HTTPException(409, "Esse corte já está renderizando. Espere terminar.")

    clip.title = title
    clip.description = body.description.strip()
    clip.hashtags = clean_hashtags(body.hashtags)
    session.add(clip)
    session.commit()
    if needs_render:
        if not times_changed:
            start, end = clip.start_s, clip.end_s
        payload = {
            "clip_id": clip.id,
            "start_s": start,
            "end_s": min(end, video.duration_s or end),
            "zoom": framing.zoom,
            "pan_x": framing.pan_x,
            "pan_y": framing.pan_y,
            "captions": captions,
        }
        queue.enqueue(session, RENDER_CLIP, payload)
    session.refresh(clip)
    return _studio(session, clip, video)


@router.get("/{clip_id}/autoframe")
def autoframe(clip_id: int, session: SessionDep, start_s: float, end_s: float) -> AutoFrameOut:
    """Suggest zoom/pan from black bars in the original (ffmpeg cropdetect)."""
    _clip, video = _load(session, clip_id)
    src = Path(video.file_path or "")
    if not video.file_path or not src.exists():
        raise HTTPException(409, "O vídeo original não está no disco; ajuste o zoom na mão.")
    try:
        width, height = framing_detect.probe_size(src)
        box = framing_detect.detect_content(src, start_s, end_s)
    except CommandError as exc:
        raise HTTPException(500, f"Não consegui analisar o vídeo: {exc}") from exc
    suggestion = framing_detect.suggest(width, height, box) if box else None
    if suggestion is None:
        return AutoFrameOut(
            found=False,
            message="Não achei barras pretas nas laterais. Se as bordas são desfocadas, "
            "ajuste o zoom na mão.",
        )
    return AutoFrameOut(
        found=True,
        zoom=suggestion.zoom,
        pan_x=suggestion.pan_x,
        pan_y=suggestion.pan_y,
        message=f"Área com imagem encontrada: zoom {suggestion.zoom:.2f}x.",
    )
