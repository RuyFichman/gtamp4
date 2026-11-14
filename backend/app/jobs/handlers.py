"""Job handlers. Imported once at startup so the @handler decorators register them."""

from pathlib import Path

from sqlmodel import Session, select

from app.config import get_settings
from app.jobs import queue
from app.jobs.worker import handler
from app.models import Clip, FrameTemplate, Job, SourceVideo, utcnow
from app.pipeline import cut, download, energy, score, transcribe

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
        segments, lang = transcribe.whisper_transcribe(path, info.language)
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
            description=video.description,
            views=video.views,
            segments=segments,
            energy=loud,
            duration=video.duration_s,
        )
    else:
        ideas = score.plan_heuristic(video.title, segments, loud, video.duration_s)

    if not ideas:
        _step(session, job, 1.0, "Nenhum trecho bom encontrado")
        return

    frame = _default_frame(session)
    for i, idea in enumerate(ideas, 1):
        _step(session, job, 0.6 + 0.4 * (i - 1) / len(ideas), f"Cortando {i} de {len(ideas)}")
        dst = settings.clips_dir / f"{video.youtube_id}_{idea.start_s:.0f}-{idea.end_s:.0f}.mp4"
        cut.render_clip(path, dst, idea.start_s, idea.end_s, frame)
        clip = Clip(
            source_video_id=video.id or 0,
            start_s=idea.start_s,
            end_s=idea.end_s,
            title=idea.title,
            description=idea.description,
            hashtags=idea.hashtags,
            potential=idea.potential,
            potential_reason=idea.reason,
            file_path=str(dst),
        )
        session.add(clip)
        session.commit()
