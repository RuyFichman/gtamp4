"""Smarter picking: YouTube "most replayed" + chapters, pause snapping, editor feedback."""

from collections.abc import Iterator
from pathlib import Path
from typing import get_args

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import feedback
from app.api import clips
from app.db import get_session
from app.jobs import handlers, queue
from app.models import Clip, ClipStatus, SourceVideo
from app.pipeline import boundaries, captions, cut, download, energy, score
from app.pipeline import transcribe as transcribe_mod
from app.pipeline.download import parse_chapters, parse_heatmap
from app.pipeline.types import Chapter, HeatPoint, Segment, Word

# --- most replayed + chapters -------------------------------------------------------------


def test_parse_heatmap_and_chapters_skip_bad_entries() -> None:
    info = {
        "heatmap": [
            {"start_time": 0, "end_time": 2.38, "value": 0.26},
            {"start_time": 2.38, "end_time": "x", "value": 1},
        ],
        "chapters": [{"start_time": 0, "end_time": 43, "title": "Intro"}, {"title": "sem tempo"}],
    }
    assert parse_heatmap(info) == [HeatPoint(start=0, end=2.38, value=0.26)]
    assert parse_chapters(info) == [Chapter(start=0, end=43, title="Intro")]
    assert parse_heatmap({}) == [] and parse_chapters({"chapters": None}) == []


def test_replay_per_second_is_normalized() -> None:
    heat = [HeatPoint(start=0, end=2, value=0.2), HeatPoint(start=2, end=4, value=0.5)]
    out = score.replay_per_second(heat, 5)
    assert out.tolist() == pytest.approx([0.4, 0.4, 1.0, 1.0, 0.0])
    assert score.replay_per_second([], 10).size == 0


def test_transcript_gets_replay_column_and_chapter_lines() -> None:
    segments = [
        Segment(start=0, end=2, text="oi"),
        Segment(start=2, end=4, text="olha isso"),
        Segment(start=40, end=42, text="próximo"),
    ]
    energy = np.full(50, 0.5)
    replay = np.zeros(50)
    replay[2:4] = 1.0
    chapters = [Chapter(start=0, end=39, title="Intro"), Chapter(start=39, end=50, title="Mapa")]
    text = score.format_transcript(segments, energy, replay, chapters).splitlines()
    assert text[0] == "=== Capítulo (00:00): Intro ==="
    assert "energia=4 replay=0 | oi" in text[1]
    assert "replay=9 | olha isso" in text[2]
    assert text[3] == "=== Capítulo (00:39): Mapa ==="
    # no graph: no column, so the prompt's "sem a coluna" rule applies
    assert "replay" not in score.format_transcript(segments, energy)


def test_heuristic_follows_replay_when_loudness_is_flat() -> None:
    energy = np.full(200, 0.5)
    replay = np.zeros(200)
    replay[120:160] = 1.0
    ideas = score.plan_heuristic("t", [], energy, 200, score.ClipLimits(12, 40, 1), replay)
    assert ideas[0].start_s == 120
    assert "mais repetido" in ideas[0].reason


def test_user_message_puts_examples_before_transcript() -> None:
    msg = score.user_message(
        title="T",
        channel="C",
        language="en",
        description="d",
        views=1,
        transcript="[0.0-1.0] linha",
        examples="Decisões do editor (...):",
    )
    assert msg.index("Decisões do editor") < msg.index("Transcrição")
    assert "Decisões" not in score.user_message(
        title="T", channel="C", language=None, description="", views=None, transcript="x"
    )


# --- edge snapping ------------------------------------------------------------------------


def w(start: float, end: float, word: str) -> Word:
    return Word(start=start, end=end, word=word)


WORDS = [
    w(7.0, 7.5, "e"), w(7.5, 7.9, "aí"), w(8.0, 8.4, "acabou."),   # sentence end, 0.5 s pause
    w(8.9, 9.3, "Olha"), w(9.3, 9.6, "só"), w(9.6, 10.0, "isso,"),  # comma, tiny gap
    w(10.05, 10.5, "vazou"), w(10.5, 11.0, "o"), w(11.0, 11.4, "mapa"),
]  # fmt: skip


def test_start_prefers_sentence_end_over_nearer_tiny_gap() -> None:
    # the AI said 10.0 (between "isso," and "vazou"); the sentence starts at "Olha"
    assert boundaries.snap_start(WORDS, 10.0) == pytest.approx(8.8)  # breath before "Olha"


def test_end_lands_after_the_last_word_never_inside_the_next() -> None:
    assert boundaries.snap_end(WORDS, 8.7) == pytest.approx(8.65)  # "acabou." + 0.25
    tight = [w(0, 1, "um."), w(1.1, 2, "dois")]
    assert boundaries.snap_end(tight, 1.0) == pytest.approx(1.1)  # gap shorter than the tail


def test_split_word_is_not_a_break_and_window_edge_is() -> None:
    # Whisper split "GTA6" into "GT" + "-A6", with a gap; the video's speech starts at "GT"
    words = [w(5.4, 5.6, "GT"), w(5.8, 6.1, "-A6"), w(6.1, 6.4, "já"), w(6.4, 6.8, "é")]
    assert boundaries.snap_start(words, 5.7, window=(2.7, 9.0)) == pytest.approx(5.3)


def test_snap_keeps_time_without_words_nearby() -> None:
    assert boundaries.snap_start([], 12.3) == 12.3
    assert boundaries.snap_end(WORDS, 30.0) == 30.0  # nothing within MAX_SHIFT_S


def test_snap_clip_respects_length_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    # a 30 s clip that each edge would grow by 1 s
    monkeypatch.setattr(boundaries, "snap_start", lambda _w, t, _win: t - 1)
    monkeypatch.setattr(boundaries, "snap_end", lambda _w, t, _win: t + 1)
    assert boundaries.snap_clip([], 10, 40, 12, 32) == (9, 41)
    assert boundaries.snap_clip([], 10, 40, 12, 31) == (10, 41)  # only the end
    assert boundaries.snap_clip([], 10, 40, 12, 30) == (10, 40)  # keep the AI's


def test_process_video_snaps_edges_and_reuses_words_for_captions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    src = tmp_path / "vid.mp4"
    src.write_bytes(b"x")
    info = download.VideoInfo(
        youtube_id="vid", title="T", channel="C", description="", duration_s=100, views=1,
        language="pt", heatmap=[HeatPoint(start=0, end=50, value=1.0)],
        chapters=[Chapter(start=0, end=100, title="Tudo")],
    )  # fmt: skip
    seen: dict[str, object] = {}
    idea = score.ClipIdea(start_s=10.0, end_s=30.0, potential=80, reason="r", title="t",
                          description="d", hashtags=[])  # fmt: skip
    words = WORDS + [w(29.0, 29.6, "fim."), w(30.4, 31.0, "Depois")]

    def plan(**kw: object) -> list[score.ClipIdea]:
        seen.update(kw)
        return [idea]

    def transcribe(_model: object, _src: Path, lo: float, hi: float, lang: str | None) -> list:
        seen.setdefault("windows", []).append((lo, hi, lang))  # type: ignore[union-attr]
        return words

    def render(*args: object, **kw: object) -> None:
        seen["render"] = args, kw

    monkeypatch.setattr(download, "fetch_info", lambda _url: info)
    monkeypatch.setattr(download, "download_video", lambda *_a: src)
    monkeypatch.setattr(transcribe_mod, "whisper_transcribe", lambda *_a: ([], "pt"))
    monkeypatch.setattr(energy, "loudness_per_second", lambda _p: np.full(100, 0.5))
    monkeypatch.setattr(score, "plan_with_claude", plan)
    monkeypatch.setattr(score, "plan_heuristic", lambda *a: plan(replay=a[-1]))
    monkeypatch.setattr(captions, "load_whisper", lambda _size: object())
    monkeypatch.setattr(captions, "transcribe_words", transcribe)
    monkeypatch.setattr(cut, "render_clip", render)

    with Session(engine) as s:
        job = queue.enqueue(s, handlers.PROCESS_VIDEO, {"url": "https://youtu.be/vid"})
        handlers.process_video(s, job)
        clip = s.exec(select(Clip)).one()
        video = s.exec(select(SourceVideo)).one()

        assert seen["windows"] == [(7.0, 33.0, "pt")]  # one Whisper pass, with margin
        assert (clip.start_s, clip.end_s) == (8.8, pytest.approx(29.85))  # "Olha" … "fim."
        assert clip.caption_range == [7.0, 33.0]  # cached for the caption and the Studio
        assert (clip.ai_start_s, clip.ai_end_s) == (clip.start_s, clip.end_s)  # delivered
        args, kw = seen["render"]  # type: ignore[misc]
        assert args[2:4] == (8.8, pytest.approx(29.85))
        assert "OLHA" in kw["ass"]
        replay = seen["replay"]
        assert isinstance(replay, np.ndarray) and replay[:50].min() == 1.0
        assert video.heatmap and video.chapters == [{"start": 0, "end": 100, "title": "Tudo"}]


# --- rejection reasons + editor examples ---------------------------------------------------


def test_reject_reason_keys_match_labels() -> None:
    assert set(get_args(feedback.RejectReason)) == set(feedback.REJECT_REASONS)


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        words = " ".join(f"palavra{i}" for i in range(120))
        a = SourceVideo(
            youtube_id="a",
            url="u",
            title="Vazou o mapa",
            transcript=[
                {"start": 0, "end": 10, "text": "Olha isso, vazou o mapa"},
                {"start": 10, "end": 30, "text": words},
                {"start": 30, "end": 40, "text": "fora do corte"},
            ],
        )
        b = SourceVideo(youtube_id="b", url="u", title="Outro")
        s.add_all([a, b])
        s.commit()
        s.add_all(
            [
                Clip(source_video_id=a.id or 0, start_s=0, end_s=30, potential=70,
                     status=ClipStatus.POSTED),
                Clip(source_video_id=a.id or 0, start_s=0, end_s=10, potential=85,
                     status=ClipStatus.REJECTED, reject_reason="no_context"),
                Clip(source_video_id=a.id or 0, start_s=10, end_s=20, potential=60,
                     status=ClipStatus.REJECTED),
                Clip(source_video_id=b.id or 0, start_s=0, end_s=20, potential=50),
            ]
        )  # fmt: skip
        s.commit()
    return engine


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    def session_override() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app = FastAPI()
    app.include_router(clips.router)
    app.dependency_overrides[get_session] = session_override
    yield TestClient(app)


def test_editor_examples_show_verdict_reason_and_words(engine: Engine) -> None:
    with Session(engine) as s:
        text = feedback.editor_examples(s)
        lines = text.splitlines()
        assert lines[0].startswith("Decisões do editor")
        assert "APROVADO E POSTADO | nota que a IA deu: 70 | 30 s" in text
        # reasoned rejection comes before the bare one
        bare = text.index("RECUSADO | nota que a IA deu: 60")
        assert text.index("RECUSADO (sem contexto:") < bare
        assert "Olha isso, vazou o mapa palavra0" in text and "palavra119" in text
        assert " … " in text and "fora do corte" not in text  # long clip: head … tail
        assert "Motivos de recusa mais comuns até agora: sem contexto (1)." in text
        # pending clips never show up; the video being processed is left out
        assert feedback.editor_examples(s, exclude_video_id=1) == ""


def test_reject_with_reason_and_clear_it_on_return(client: TestClient, engine: Engine) -> None:
    reasons = client.get("/api/clips/reject-reasons").json()
    assert {"key": "cut_mid", "label": "Cortou no meio"} in reasons

    r = client.post("/api/clips/4/status", json={"status": "rejected", "reject_reason": "weak"})
    assert r.status_code == 200 and r.json()["reject_reason"] == "weak"
    bad = client.post("/api/clips/4/status", json={"status": "rejected", "reject_reason": "x"})
    assert bad.status_code == 422

    client.post("/api/clips/4/status", json={"status": "pending_review", "reject_reason": "weak"})
    with Session(engine) as s:
        clip = s.get(Clip, 4)
        assert clip is not None and clip.reject_reason is None


def test_approved_clip_shows_how_the_editor_moved_its_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        v = SourceVideo(
            youtube_id="v",
            url="u",
            title="Mapa",
            transcript=[
                {"start": 0, "end": 4, "text": "bom, então"},
                {"start": 4, "end": 20, "text": "vazou o mapa inteiro"},
                {"start": 20, "end": 26, "text": "e outra coisa que eu queria falar"},
            ],
        )
        s.add(v)
        s.commit()
        vid = v.id or 0
        s.add_all(
            [
                # editor trimmed the filler at the start and the new topic at the end
                Clip(source_video_id=vid, start_s=4, end_s=20, ai_start_s=0, ai_end_s=26,
                     potential=80, status=ClipStatus.APPROVED),
                # untouched (tiny move is noise) and an old clip without the record
                Clip(source_video_id=vid, start_s=4.2, end_s=20, ai_start_s=4, ai_end_s=20,
                     potential=70, status=ClipStatus.POSTED),
                Clip(source_video_id=vid, start_s=4, end_s=20, potential=60,
                     status=ClipStatus.APPROVED),
            ]
        )  # fmt: skip
        s.commit()
        text = feedback.editor_examples(s)

    first = text.splitlines()[1]
    assert first.startswith("- APROVADO APÓS AJUSTE DO EDITOR | nota que a IA deu: 80")
    assert 'começou 4 s cedo demais; o editor tirou do início. Trecho: "bom, então"' in text
    assert (
        "terminou 6 s depois do ponto certo; o editor tirou do fim. "
        'Trecho: "e outra coisa que eu queria falar"'
    ) in text
    assert text.count("APÓS AJUSTE") == 1 and text.count("ajuste do editor:") == 2
    assert "Ajustes do editor" not in text  # 2 clips with the record: below TREND_MIN_CLIPS

    monkeypatch.setattr(feedback, "TREND_MIN_CLIPS", 2)
    with Session(engine) as s:
        assert feedback.adjustment_trend(s) == (
            "Ajustes do editor nos 2 cortes aprovados: atrasou o começo em 1 (em média 4 s), "
            "encurtou o fim em 1 (em média 6 s)."
        )
