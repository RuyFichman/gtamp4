"""Job handlers. Imported once at startup so the @handler decorators register them."""

from pathlib import Path

from sqlmodel import Session, col, select

from app.config import get_settings
from app.jobs import queue
from app.jobs.worker import handler
from app.models import Clip, FrameTemplate, Job, JobStatus, SourceVideo, utcnow
from app.pipeline import cut, download, energy, score, transcribe
from app.store import get_app_config

PROCESS_VIDEO = "process_video"


def _step(session: Session, job: Job, progress: float, message: str) -> None:
    queue.update(session, job, progress=progress, message=message)


def _default_frame(session: Session) -> Path | None:
    frame = session.exec(select(FrameTemplate).where(FrameTemplate.is_default)).first()
    if frame and Path(frame.overlay_path).exists():
        return Path(frame.overlay_path)
    return None


@handler(PROCESS_VIDEO)
def process_video(session: Session, job: Job) -> None:
    settings = get_settings()
    cfg = get_app_config(session)
    limits = score.ClipLimits(cfg.min_clip_s, cfg.max_clip_s, cfg.max_clips)
    url = job.payload["url"]

    _step(session, job, 0.02, "Lendo informações do vídeo")
    info = download.fetch_info(url)
    queue.update(session, job, payload={**job.payload, "title": info.title})

    video = session.exec(
        select(SourceVideo).where(SourceVideo.youtube_id == info.youtube_id)
    ).first() or SourceVideo(
        youtube_id=info.youtube_id, url=download.canonical_url(info.youtube_id)
    )
    video.title = info.title
    video.channel = info.channel
    video.description = info.description
    video.duration_s = info.duration_s
    video.views = info.views
    video.views_checked_at = utcnow()
    video.language = info.language
    session.add(video)
    session.commit()
    session.refresh(video)

    _step(session, job, 0.1, "Baixando vídeo")
    path = download.download_video(video.url, settings.videos_dir, video.youtube_id)
    video.file_path = str(path)

    _step(session, job, 0.35, "Transcrevendo")
    if video.transcript:
        segments = video.transcript
    elif info.subtitle_json3:
        segments = transcribe.parse_json3(info.subtitle_json3)
    else:
        _step(session, job, 0.35, "Transcrevendo com Whisper (sem legenda no YouTube)")
        segments, lang = transcribe.whisper_transcribe(path, info.language, cfg.whisper_model)
        video.language = video.language or lang
    video.transcript = list(segments)
    session.add(video)
    session.commit()

    _step(session, job, 0.5, "Medindo energia do áudio")
    loud = energy.loudness_per_second(path)

    if settings.anthropic_api_key:
        _step(session, job, 0.55, "Analisando com IA")
        ideas = score.plan_with_claude(
            title=video.title,
            channel=video.channel,
            language=video.language,
            description=video.description,
            views=video.views,
            segments=segments,
            energy=loud,
            duration=video.duration_s,
            limits=limits,
            model=cfg.model_writer,
        )
    else:
        ideas = score.plan_heuristic(video.title, segments, loud, video.duration_s, limits)

    if not ideas:
        _step(session, job, 1.0, "Nenhum trecho bom encontrado")
        return

    frame = _default_frame(session)
    for i, idea in enumerate(ideas, 1):
        _step(session, job, 0.6 + 0.4 * (i - 1) / len(ideas), f"Cortando {i} de {len(ideas)}")
        dst = settings.clips_dir / f"{video.youtube_id}_{idea.start_s:.0f}-{idea.end_s:.0f}.mp4"
        cut.render_clip(path, dst, idea.start_s, idea.end_s, frame, cfg.video_encoder)
        # reprocessing the same video must not duplicate a clip (keeps its status)
        clip = session.exec(select(Clip).where(Clip.file_path == str(dst))).first() or Clip(
            source_video_id=video.id or 0, start_s=idea.start_s, end_s=idea.end_s
        )
        clip.title = idea.title
        clip.description = idea.description
        clip.hashtags = idea.hashtags
        clip.potential = idea.potential
        clip.potential_reason = idea.reason
        clip.file_path = str(dst)
        session.add(clip)
        session.commit()


RENDER_CLIP = "render_clip"
STUDIO_MIN_S = 3.0
STUDIO_MAX_S = 180.0


def pending_renders(session: Session) -> dict[int, Job]:
    """Studio re-renders not finished yet, by clip id."""
    jobs = session.exec(
        select(Job).where(
            Job.kind == RENDER_CLIP,
            col(Job.status).in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    ).all()
    return {job.payload["clip_id"]: job for job in jobs}


def studio_clip_path(youtube_id: str, clip_id: int, start: float, end: float) -> Path:
    # clip id in the name: an edited clip never collides with another clip's file
    return get_settings().clips_dir / f"{youtube_id}_{clip_id}_{start:.1f}-{end:.1f}.mp4"


@handler(RENDER_CLIP)
def render_clip(session: Session, job: Job) -> None:
    """Studio: re-cut a clip with new start/end. The clip only changes after a good render."""
    clip = session.get(Clip, job.payload["clip_id"])
    if clip is None:
        raise RuntimeError("Esse corte não existe mais.")
    video = session.get(SourceVideo, clip.source_video_id)
    if video is None:
        raise RuntimeError("O vídeo original desse corte não está no banco.")
    start, end = float(job.payload["start_s"]), float(job.payload["end_s"])
    queue.update(session, job, payload={**job.payload, "title": f"Estúdio: {clip.title}"})

    src = Path(video.file_path) if video.file_path else None
    if src is None or not src.exists():
        _step(session, job, 0.1, "Baixando o vídeo original de novo")
        src = download.download_video(video.url, get_settings().videos_dir, video.youtube_id)
        video.file_path = str(src)
        session.add(video)
        session.commit()

    _step(session, job, 0.4, "Renderizando")
    dst = studio_clip_path(video.youtube_id, clip.id or 0, start, end)
    encoder = get_app_config(session).video_encoder
    cut.render_clip(src, dst, start, end, _default_frame(session), encoder)

    old = Path(clip.file_path) if clip.file_path else None
    clip.start_s, clip.end_s, clip.file_path = start, end, str(dst)
    session.add(clip)
    session.commit()
    if old and old != dst and old.exists():
        still_used = session.exec(select(Clip.id).where(Clip.file_path == str(old))).first()
        if still_used is None:
            old.unlink(missing_ok=True)
