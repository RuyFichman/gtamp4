"""Commented gameplay only: transcript hygiene, speech metrics, the Radar title filter and
triage, `has_commentary`, and the guards in process_video. No network, ffmpeg or Claude."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import feedback
from app.api import clips as clips_api
from app.config import get_settings
from app.jobs import handlers, queue
from app.jobs.worker import process_one
from app.models import Clip, ClipStatus, Job, JobStatus, SourceVideo
from app.pipeline import captions, cut, download, energy, radar, score, speech, triage
from app.pipeline import transcribe as transcribe_mod
from app.pipeline.radar import Found
from app.pipeline.transcribe import parse_json3
from app.pipeline.types import Segment, Word


def seg(start: float, end: float, text: str) -> Segment:
    return Segment(start=start, end=end, text=text)


def word(start: float, end: float, text: str = "palavra") -> Word:
    return Word(start=start, end=end, word=text)


def chatter(start: float, end: float) -> list[Word]:
    """Whisper words of someone talking non-stop: 2 words/s."""
    return [word(t, t + 0.4) for t in np.arange(start, end, 0.5).tolist()]


def json3(lines: list[tuple[float, float, str]]) -> dict[str, Any]:
    return {
        "events": [
            {"tStartMs": int(a * 1000), "dDurationMs": int((b - a) * 1000), "segs": [{"utf8": t}]}
            for a, b, t in lines
        ]
    }


NARRATED_SUBS = json3([(t, t + 2, "olha só que coisa louca") for t in range(0, 100, 2)])


# --- transcript hygiene ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "[Music]", "[Música]", "[Musique]", "[Applause]", "[Aplausos]", "[Laughter]", "[Risos]",
        "[risadas]", "[Risas]", "[Música] [Aplausos]", "♪", "♪♪♪", "♪ we ride tonight ♪",
        "♪ la la la", "(risos)", "(music playing)", "(Música)", ">>",
    ],
)  # fmt: skip
def test_cue_only_lines_are_not_speech(raw: str) -> None:
    assert speech.clean_text(raw) == ""


def test_cues_are_stripped_inline_and_said_words_stay() -> None:
    assert speech.clean_text("[Música] olha isso [Aplausos] cara") == "olha isso cara"
    assert speech.clean_text("That's insane [Laughter]") == "That's insane"
    assert speech.clean_text("no puede ser (risas) mira") == "no puede ser mira"
    assert speech.clean_text("♪ la la ♪ e agora?") == "e agora?"
    assert speech.clean_text("e agora ♪ we ride tonight") == "e agora"
    # YouTube's censored swear word was said (loudly): it stays and counts
    assert speech.clean_text("Que [ __ ] é essa") == "Que [ __ ] é essa"
    assert speech.word_count("Que [ __ ] é essa") == 4
    assert speech.word_count(">> - …") == 0


def test_clean_segments_drops_cue_lines_and_is_idempotent() -> None:
    segments = [seg(0, 2, "[Music]"), seg(2, 4, "[Música] bora"), seg(4, 6, "♪")]
    out = speech.clean_segments(segments)
    assert out == [seg(2, 4, "bora")]
    assert speech.clean_segments(out) == out


def test_parse_json3_drops_music_and_the_line_before_ends_where_it_starts() -> None:
    segments = parse_json3(
        json3([(0, 9, "bora testar"), (3, 23, "[Música]"), (23, 25, "[Applause] caramba")])
    )
    assert segments == [seg(0, 3, "bora testar"), seg(23, 25, "caramba")]


# --- speech metrics --------------------------------------------------------------------------


def test_video_metrics_merge_overlapping_lines() -> None:
    segments = [seg(0, 10, "a b c d e"), seg(5, 15, "f g h i j"), seg(50, 60, "k l m n o")]
    assert speech.speech_coverage(segments, 100) == pytest.approx(0.25)
    assert speech.words_per_minute(segments, 100) == pytest.approx(9.0)
    assert speech.speech_coverage(segments, None) == pytest.approx(25 / 60)  # up to last line
    assert speech.speech_coverage([], 100) == 0 and speech.words_per_minute([], None) == 0
    assert not speech.video_speech(segments, 100).narrated
    talk = [seg(t, t + 2, "uma frase de cinco palavras") for t in range(0, 100, 2)]
    assert speech.video_speech(talk, 100).narrated


def test_window_metrics_on_segments() -> None:
    segments = [seg(0, 10, "um dois três quatro cinco seis sete oito nove dez"), seg(30, 40, "x y")]
    # half of each line falls in the window: 5 + 1 words over 30 s
    assert speech.window_words_per_second(segments, 5, 35) == pytest.approx(0.2)
    assert speech.longest_silence(segments, 5, 35) == pytest.approx(20)  # 10 -> 30
    assert speech.longest_silence(segments, 0, 55) == pytest.approx(20)  # edge 40 -> 55 is 15
    assert speech.longest_silence(segments, 12, 20) == pytest.approx(8)  # nobody talks at all
    assert speech.window_words_per_second(segments, 20, 20) == 0


def test_window_metrics_on_whisper_words() -> None:
    words = [word(1.0, 1.4, "olha"), word(1.4, 1.8, "isso"), word(9.0, 9.5, "caramba!")]
    assert speech.window_words_per_second(words, 0, 10) == pytest.approx(0.3)
    assert speech.longest_silence(words, 0, 10) == pytest.approx(7.2)  # 1.8 -> 9.0
    assert not speech.clip_speech(words, 0, 10).narrated
    talk = speech.clip_speech(chatter(0, 20), 0, 20)
    assert talk.wps == pytest.approx(2.0) and talk.narrated
    # a long silent stretch fails even with plenty of words around it
    gap = chatter(0, 10) + chatter(10 + speech.CLIP_MAX_SILENCE_S + 1, 40)
    assert not speech.clip_speech(gap, 0, 40).narrated


def test_spans_can_be_counted_once_and_reused() -> None:
    words = chatter(0, 20)
    timed = speech.spans(words)
    assert speech.spans(timed) == timed
    assert speech.clip_speech(timed, 0, 20) == speech.clip_speech(words, 0, 20)


# --- Radar: title prefilter and triage -------------------------------------------------------


def found(title: str, vid: str = "a") -> Found:
    return Found(youtube_id=vid, url="u", title=title, channel="C", duration_s=600, views=100)


@pytest.mark.parametrize(
    "title",
    [
        "GTA 6 Walkthrough Part 1 No Commentary 4K",
        "GTA 6 - Full Game (No-Commentary) PS5 Pro",
        "GTA VI Gameplay Without Commentary",
        "GTA VI Gameplay sem comentários [4K]",
        "GTA 6 gameplay sem narração",
        "GTA 6 Misión 3 sin comentarios",
        "GTA 6 All Cutscenes (Full Game Movie)",
        "GTA 6 - Todas as Cutscenes",
        "GTA VI - Película completa en español",
        "GTA 6 O Filme Completo",
    ],
)
def test_prefilter_rejects_titles_that_say_nobody_talks(title: str) -> None:
    assert radar.prefilter(found(title)) == "Gameplay sem narração (título)"


@pytest.mark.parametrize(
    "title",
    [
        "GTA 6 gameplay comentado",
        "Reagindo ao GTA 6",
        "GTA 6 Walkthrough Part 1 [4K 60FPS]",  # ambiguous: the AI triage judges it
        "GTA 6 Longplay",
        "Rockstar has no comment on the GTA 6 delay",
        "I played GTA 6 for 10 hours - my honest commentary",
        "GTA 6: comentários sobre o mapa",
    ],
)
def test_prefilter_lets_commented_or_ambiguous_titles_through(title: str) -> None:
    assert radar.prefilter(found(title)) is None


def test_heuristic_triage_rejects_no_commentary_titles() -> None:
    out = triage.triage_heuristic(
        [found("GTA 6 Walkthrough No Commentary", "a"), found("Reagindo ao GTA 6", "b")]
    )
    assert not out["a"].keep and "sem narração" in out["a"].reason
    assert out["b"].keep


def test_triage_prompt_is_about_commented_gameplay() -> None:
    assert "Gameplay puro" in triage.SYSTEM_PROMPT
    assert "vazamentos" not in triage.SYSTEM_PROMPT  # pre-launch focus is gone


# --- AI: silence markers and has_commentary --------------------------------------------------


def test_transcript_marks_long_speechless_stretches() -> None:
    segments = [seg(8, 10, "começou"), seg(11, 13, "olha"), seg(31, 33, "caramba")]
    lines = score.format_transcript(segments, np.zeros(0), duration=60).splitlines()
    assert lines[0] == "[... 8 s sem fala ...]"  # from the start of the video
    assert "começou" in lines[1] and "olha" in lines[2]  # a 1 s pause gets no marker
    assert lines[3] == "[... 18 s sem fala ...]"
    assert "caramba" in lines[4]
    assert lines[5] == "[... 27 s sem fala ...]"  # up to the end of the video
    assert "sem fala" not in score.format_transcript(segments[:2], np.zeros(0)).split("\n", 1)[1]


def test_has_commentary_is_decided_before_the_clips() -> None:
    assert list(score.ClipPlan.model_fields) == ["video_language", "has_commentary", "clips"]


IDEA = score.ClipIdea(
    start_s=10, end_s=40, potential=80, reason="r", title="t", description="d", hashtags=["#x"]
)


def fake_anthropic(plan: score.ClipPlan, seen: dict[str, Any]) -> Any:
    def parse(**kw: Any) -> Any:
        seen.update(kw)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=plan)

    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)))


@pytest.mark.parametrize("has_commentary", [False, True])
def test_no_commentator_means_zero_clips_whatever_the_ai_returned(
    monkeypatch: pytest.MonkeyPatch, has_commentary: bool
) -> None:
    plan = score.ClipPlan(video_language="en", has_commentary=has_commentary, clips=[IDEA])
    seen: dict[str, Any] = {}
    monkeypatch.setattr(score.anthropic, "Anthropic", lambda **_kw: fake_anthropic(plan, seen))
    out = score.plan_with_claude(
        title="GTA 6 Walkthrough Part 1", channel="C", language="en", description="", views=1,
        segments=[seg(0, 30, "We need that money, Jason.")], energy=np.zeros(0), duration=60,
        limits=score.ClipLimits(), model="m",
    )  # fmt: skip
    assert out.has_commentary is has_commentary
    assert out.clips == ([IDEA.model_copy(update={"hashtags": ["x"]})] if has_commentary else [])
    assert "has_commentary" in seen["system"]
    assert f"{speech.CLIP_MAX_SILENCE_S:.0f} s seguidos sem fala" in seen["system"]
    assert "[... 30 s sem fala ...]" in seen["messages"][0]["content"]


# --- process_video guards --------------------------------------------------------------------


@dataclass
class Pipeline:
    """process_video with every outside call faked; tweak the fields, then run()."""

    session: Session
    info: download.VideoInfo
    whisper: list[Segment] = field(default_factory=list)
    words: list[Word] = field(default_factory=list)
    plan: score.ClipPlan | None = None
    downloads: int = 0
    plans: int = 0
    renders: list[tuple[Any, ...]] = field(default_factory=list)

    def run(self) -> Job:
        queue.enqueue(self.session, handlers.PROCESS_VIDEO, {"url": "https://youtu.be/vid"})
        assert process_one(self.session)
        job = self.session.exec(select(Job)).one()
        assert job.status == JobStatus.DONE, job.error
        return job

    def clips(self) -> list[Clip]:
        return list(self.session.exec(select(Clip)).all())


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Pipeline]:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # fake: plan_with_claude is replaced
    get_settings.cache_clear()
    engine = create_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    src = tmp_path / "vid.mp4"
    src.write_bytes(b"x")
    info = download.VideoInfo(
        youtube_id="vid", title="T", channel="C", description="", duration_s=100, views=1,
        language="pt",
    )  # fmt: skip
    with Session(engine) as session:
        p = Pipeline(session=session, info=info)

        def fake_download(*_a: object) -> Path:
            p.downloads += 1
            return src

        def fake_plan(**_kw: object) -> score.ClipPlan | None:
            p.plans += 1
            return p.plan

        def fake_words(_m: object, _src: Path, lo: float, hi: float, _lang: object) -> list:
            return [w for w in p.words if lo <= w["start"] < hi]

        monkeypatch.setattr(download, "fetch_info", lambda _url: p.info)
        monkeypatch.setattr(download, "download_video", fake_download)
        monkeypatch.setattr(transcribe_mod, "whisper_transcribe", lambda *_a: (p.whisper, "pt"))
        monkeypatch.setattr(energy, "loudness_per_second", lambda _p: np.full(100, 0.5))
        monkeypatch.setattr(score, "plan_with_claude", fake_plan)
        monkeypatch.setattr(captions, "load_whisper", lambda _size: object())
        monkeypatch.setattr(captions, "transcribe_words", fake_words)
        monkeypatch.setattr(cut, "render_clip", lambda *a, **_kw: p.renders.append(a))
        yield p
    get_settings.cache_clear()


def test_video_guard_stops_before_download_when_subtitles_have_no_speech(
    pipeline: Pipeline,
) -> None:
    # walkthrough with no commentary: YouTube heard music and one NPC line
    pipeline.info.subtitle_json3 = json3([(0, 100, "[Music]"), (40, 42, "Hey, watch it!")])
    job = pipeline.run()
    assert pipeline.downloads == 0 and pipeline.plans == 0 and pipeline.renders == []
    assert job.message.startswith(handlers.NO_SPEECH)
    assert "fala em 2% do vídeo" in job.message
    video = pipeline.session.exec(select(SourceVideo)).one()
    assert video.transcript == [{"start": 40.0, "end": 42.0, "text": "Hey, watch it!"}]
    assert pipeline.clips() == []


def test_video_guard_after_whisper_when_there_are_no_subtitles(pipeline: Pipeline) -> None:
    pipeline.whisper = [seg(50, 52, "Lucia, cuidado!")]  # a cutscene line, nothing else
    job = pipeline.run()
    assert pipeline.downloads == 1 and pipeline.plans == 0 and pipeline.renders == []
    assert job.message.startswith(handlers.NO_SPEECH)


def test_ai_without_commentator_means_zero_clips(pipeline: Pipeline) -> None:
    # cutscenes all along: plenty of speech, nobody commenting
    pipeline.info.subtitle_json3 = NARRATED_SUBS
    pipeline.plan = score.ClipPlan(video_language="pt", has_commentary=False, clips=[IDEA])
    job = pipeline.run()
    assert pipeline.plans == 1 and pipeline.renders == [] and pipeline.clips() == []
    assert job.message == handlers.NO_COMMENTATOR


def test_clip_guard_skips_a_speechless_window(pipeline: Pipeline) -> None:
    pipeline.info.subtitle_json3 = NARRATED_SUBS
    quiet = IDEA.model_copy(update={"start_s": 50.0, "end_s": 80.0, "title": "quiet"})
    pipeline.plan = score.ClipPlan(video_language="pt", has_commentary=True, clips=[IDEA, quiet])
    # someone talks during the first clip; in the second only two words, 28 s apart
    pipeline.words = chatter(7, 43) + [word(50.0, 50.4, "olha"), word(79.0, 79.4, "isso.")]
    job = pipeline.run()
    clips = pipeline.clips()
    assert [c.title for c in clips] == ["t"] and len(pipeline.renders) == 1
    assert clips[0].start_s >= 7 and clips[0].end_s <= 43
    assert job.message == "1 corte gerado · 1 trecho descartado: pouca narração"


def test_narrated_video_finishes_as_before(pipeline: Pipeline) -> None:
    pipeline.info.subtitle_json3 = NARRATED_SUBS
    pipeline.plan = score.ClipPlan(video_language="pt", has_commentary=True, clips=[IDEA])
    pipeline.words = chatter(0, 100)
    job = pipeline.run()
    assert job.message == "Concluído" and len(pipeline.clips()) == 1


# --- teaching the AI: "Sem narração" ---------------------------------------------------------


def test_no_commentary_reason_counts_against_the_channel() -> None:
    assert feedback.REJECT_REASONS["no_commentary"][0] == "Sem narração"
    assert "no_commentary" in get_args(feedback.RejectReason)
    assert "no_commentary" not in feedback.NOT_THE_CHANNEL

    engine = create_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        video = SourceVideo(youtube_id="v", url="u", channel="Canal Mudo")
        s.add(video)
        s.commit()
        vid = video.id or 0
        s.add_all(
            [
                Clip(source_video_id=vid, start_s=0, end_s=20, status=ClipStatus.APPROVED),
                Clip(source_video_id=vid, start_s=20, end_s=40, status=ClipStatus.REJECTED,
                     reject_reason="no_commentary"),
                Clip(source_video_id=vid, start_s=40, end_s=60, status=ClipStatus.REJECTED,
                     reject_reason="cut_mid"),  # the cut's fault: not the channel's
            ]
        )  # fmt: skip
        s.commit()
        record = feedback.channel_history(s).of("Canal Mudo")
    assert record is not None and (record.approved, record.rejected) == (1, 1)


def test_aprovar_card_gets_the_new_button() -> None:
    app = FastAPI()
    app.include_router(clips_api.router)
    reasons = TestClient(app).get("/api/clips/reject-reasons").json()
    assert {"key": "no_commentary", "label": "Sem narração"} in reasons
