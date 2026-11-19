"""Job handlers. Imported once at startup so the @handler decorators register them."""

from pathlib import Path

from sqlmodel import Session, col, select

from app import feedback
from app.config import get_settings
from app.jobs import queue
from app.jobs.worker import handler
from app.models import Clip, FrameTemplate, Job, JobStatus, SourceVideo, utcnow
from app.pipeline import boundaries, captions, cut, download, energy, score, speech, transcribe
from app.pipeline.types import Chapter, HeatPoint, Segment, Word
from app.store import AppConfig, get_app_config, get_caption_style

PROCESS_VIDEO = "process_video"

# final job messages when a video yields no clips because nobody comments over the game
NO_SPEECH = "Vídeo quase sem narração (gameplay puro): nenhum corte gerado"
NO_COMMENTATOR = (
    "A IA não achou ninguém comentando (só o jogo fala: gameplay puro ou cutscenes): "
    "nenhum corte gerado"
)


def _step(session: Session, job: Job, progress: float, message: str) -> None:
    queue.update(session, job, progress=progress, message=message)


def _keep_transcript(session: Session, video: SourceVideo, segments: list[Segment]) -> str | None:
    """Saves the transcript. Returns the final job message when the video is barely spoken
    (stop: zero clips), None to go on."""
    video.transcript = [dict(s) for s in segments]
    session.add(video)
    session.commit()
    talk = speech.video_speech(segments, video.duration_s)
    if talk.narrated:
        return None
    return f"{NO_SPEECH} · fala em {talk.coverage:.0%} do vídeo, {talk.wpm:.0f} palavras/min"


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _clips_message(made: int, skipped: int) -> str | None:
    """Final job message when clip windows were dropped for lack of narration."""
    if not skipped:
        return None
    done = _count(made, "corte gerado", "cortes gerados") if made else "Nenhum corte gerado"
    return f"{done} · {_count(skipped, 'trecho descartado', 'trechos descartados')}: pouca narração"


def _default_frame(session: Session) -> Path | None:
    frame = session.exec(select(FrameTemplate).where(FrameTemplate.is_default)).first()
    if frame and Path(frame.overlay_path).exists():
        return Path(frame.overlay_path)
    return None


class _Captioner:
    """Word timings (Whisper) for captions and edge snapping; loads Whisper once per job and
    only if a clip needs it. Words are cached on the clip with the window they cover."""

    def __init__(self, session: Session, cfg: AppConfig, src: Path, language: str | None):
        self.style = get_caption_style(session)
        self.cfg, self.src, self.language = cfg, src, language
        self._model: object | None = None

    def transcribe(self, start: float, end: float) -> list[Word]:
        if self._model is None:
            self._model = captions.load_whisper(self.cfg.whisper_model)
        return captions.transcribe_words(self._model, self.src, start, end, self.language)

    def words(self, clip: Clip, start: float, end: float) -> list[Word]:
        """Cached words if they cover [start, end]; otherwise Whisper on that window."""
        if clip.caption_words is not None and clip.caption_range:
            lo, hi = clip.caption_range
            if lo <= start + 0.01 and hi >= end - 0.01:
                return [Word(**w) for w in clip.caption_words]
        words = self.transcribe(start, end)
        clip.caption_words = [dict(w) for w in words]
        clip.caption_range = [start, end]
        return words

    def ass(self, clip: Clip, start: float, end: float) -> str:
        words = captions.clip_words(self.words(clip, start, end), start, end)
        return captions.build_ass(words, end - start, self.style)


@handler(PROCESS_VIDEO)
def process_video(session: Session, job: Job) -> str | None:
    """Link -> clips. Returns the final job message when it is worth more than "Concluído"
    (no clips, and why). Three guards keep pure gameplay out: the video's speech (before the
    download when subtitles exist), the AI's has_commentary, and each clip's narration."""
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
    # the graph shows up once a video has enough views; keep the last one we saw
    video.heatmap = [dict(h) for h in info.heatmap] or video.heatmap
    video.chapters = [dict(c) for c in info.chapters] or video.chapters
    session.add(video)
    session.commit()
    session.refresh(video)

    # transcript first when it is free (already stored, or YouTube subtitles): a video nobody
    # talks in stops here, before the download
    segments: list[Segment] | None = None
    if video.transcript:
        segments = speech.clean_segments([Segment(**s) for s in video.transcript])
    elif info.subtitle_json3:
        segments = transcribe.parse_json3(info.subtitle_json3)
    if segments is not None and (stop := _keep_transcript(session, video, segments)):
        return stop

    _step(session, job, 0.1, "Baixando vídeo")
    path = download.download_video(video.url, settings.videos_dir, video.youtube_id)
    video.file_path = str(path)
    session.add(video)
    session.commit()

    if segments is None:
        _step(session, job, 0.35, "Transcrevendo com Whisper (sem legenda no YouTube)")
        segments, lang = transcribe.whisper_transcribe(path, info.language, cfg.whisper_model)
        video.language = video.language or lang
        if stop := _keep_transcript(session, video, segments):
            return stop

    _step(session, job, 0.5, "Medindo energia do áudio")
    loud = energy.loudness_per_second(path)
    heatmap = [HeatPoint(**h) for h in video.heatmap or []]
    replay = score.replay_per_second(heatmap, int(video.duration_s or 0))
    chapters = [Chapter(**c) for c in video.chapters or []]

    if settings.anthropic_api_key:
        _step(session, job, 0.55, "Analisando com IA")
        plan = score.plan_with_claude(
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
            replay=replay,
            chapters=chapters,
            examples=feedback.editor_examples(session, exclude_video_id=video.id),
        )
        if not plan.has_commentary:
            return NO_COMMENTATOR
        ideas = plan.clips
    else:
        ideas = score.plan_heuristic(video.title, segments, loud, video.duration_s, limits, replay)

    if not ideas:
        return "Nenhum trecho bom encontrado"

    frame = _default_frame(session)
    captioner = _Captioner(session, cfg, path, video.language)
    end_limit = video.duration_s or float("inf")
    made = skipped = 0
    for i, idea in enumerate(ideas, 1):
        progress = 0.6 + 0.4 * (i - 1) / len(ideas)
        # one Whisper pass per clip, with margin: snaps the edges to the nearest sentence
        # end / pause and is reused (cache) by the burned-in captions
        _step(session, job, progress, f"Ajustando início e fim {i} de {len(ideas)}")
        lo = max(0.0, idea.start_s - boundaries.PAD_S)
        hi = min(end_limit, idea.end_s + boundaries.PAD_S)
        words = captioner.transcribe(lo, hi)
        start, end = boundaries.snap_clip(
            words, idea.start_s, idea.end_s, limits.min_s, limits.max_s, (lo, hi)
        )
        if not speech.clip_speech(words, start, end).narrated:
            skipped += 1  # mostly game audio or silence: never rendered, never a Clip
            continue
        dst = settings.clips_dir / f"{video.youtube_id}_{start:.0f}-{end:.0f}.mp4"
        # reprocessing the same video must not duplicate a clip (keeps its status)
        clip = session.exec(select(Clip).where(Clip.file_path == str(dst))).first() or Clip(
            source_video_id=video.id or 0, start_s=start, end_s=end
        )
        clip.caption_words, clip.caption_range = [dict(w) for w in words], [lo, hi]
        if clip.ai_start_s is None:
            clip.ai_start_s, clip.ai_end_s = start, end
        ass = None
        if captioner.style.enabled and clip.captions:
            _step(session, job, progress, f"Legendando {i} de {len(ideas)}")
            ass = captioner.ass(clip, start, end)
        _step(session, job, progress, f"Cortando {i} de {len(ideas)}")
        cut.render_clip(path, dst, start, end, frame, cfg.video_encoder, ass=ass)
        clip.title = idea.title
        clip.description = idea.description
        clip.hashtags = idea.hashtags
        clip.potential = idea.potential
        clip.potential_reason = idea.reason
        clip.file_path = str(dst)
        session.add(clip)
        session.commit()
        made += 1
    return _clips_message(made, skipped)


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
    p = job.payload  # framing keys are optional (e.g. Moldura re-render keeps the clip's)
    framing = cut.Framing(
        float(p.get("zoom", clip.zoom)),
        float(p.get("pan_x", clip.pan_x)),
        float(p.get("pan_y", clip.pan_y)),
    )
    want_captions = bool(p.get("captions", clip.captions))
    queue.update(session, job, payload={**job.payload, "title": f"Estúdio: {clip.title}"})

    src = Path(video.file_path) if video.file_path else None
    if src is None or not src.exists():
        _step(session, job, 0.1, "Baixando o vídeo original de novo")
        src = download.download_video(video.url, get_settings().videos_dir, video.youtube_id)
        video.file_path = str(src)
        session.add(video)
        session.commit()

    cfg = get_app_config(session)
    captioner = _Captioner(session, cfg, src, video.language)
    ass = None
    if captioner.style.enabled and want_captions:
        _step(session, job, 0.25, "Legendando")
        ass = captioner.ass(clip, start, end)

    _step(session, job, 0.4, "Renderizando")
    dst = studio_clip_path(video.youtube_id, clip.id or 0, start, end)
    if clip.file_path and Path(clip.file_path) == dst:
        # same times (e.g. new frame): never overwrite the file the user may be watching
        dst = dst.with_name(f"{dst.stem}_v{job.id}{dst.suffix}")
    cut.render_clip(src, dst, start, end, _default_frame(session), cfg.video_encoder, framing, ass)

    old = Path(clip.file_path) if clip.file_path else None
    clip.start_s, clip.end_s, clip.file_path = start, end, str(dst)
    clip.zoom, clip.pan_x, clip.pan_y = framing.zoom, framing.pan_x, framing.pan_y
    clip.captions = want_captions
    session.add(clip)
    session.commit()
    if old and old != dst and old.exists():
        still_used = session.exec(select(Clip.id).where(Clip.file_path == str(old))).first()
        if still_used is None:
            old.unlink(missing_ok=True)
