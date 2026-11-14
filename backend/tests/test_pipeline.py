from pathlib import Path

import numpy as np

from app.pipeline.cut import build_cut_command
from app.pipeline.download import _pick_subtitle_url, parse_youtube_id
from app.pipeline.energy import normalize_rms
from app.pipeline.score import ClipIdea, plan_heuristic, sanitize
from app.pipeline.transcribe import parse_json3


def test_parse_youtube_id_variants() -> None:
    vid = "ACUIYLGvGJU"
    assert parse_youtube_id(f"https://www.youtube.com/watch?v={vid}&t=10") == vid
    assert parse_youtube_id(f"https://youtu.be/{vid}") == vid
    assert parse_youtube_id(f"https://youtube.com/shorts/{vid}") == vid
    assert parse_youtube_id("https://example.com") is None


def test_subtitle_prefers_original_language_never_translation() -> None:
    info = {
        "subtitles": {},
        "automatic_captions": {
            "pt": [{"ext": "json3", "url": "translated"}],
            "en-orig": [{"ext": "vtt", "url": "x"}, {"ext": "json3", "url": "orig"}],
            "en": [{"ext": "json3", "url": "en-auto"}],
        },
    }
    assert _pick_subtitle_url(info, "en") == "orig"
    assert _pick_subtitle_url(info, None) is None


def test_parse_json3_skips_empty_and_trims_overlap() -> None:
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 4000, "segs": [{"utf8": "hello "}, {"utf8": "world"}]},
            {"tStartMs": 2000, "dDurationMs": 10, "aAppend": 1, "segs": [{"utf8": "\n"}]},
            {"tStartMs": 3000, "dDurationMs": 2000, "segs": [{"utf8": "next"}]},
            {"tStartMs": 6000},
        ]
    }
    segs = parse_json3(data)
    assert [s["text"] for s in segs] == ["hello world", "next"]
    assert segs[0]["end"] == 3.0


def test_sanitize_clamps_and_drops_short() -> None:
    ideas = [
        ClipIdea(start_s=-5, end_s=30, potential=150, reason="", title="a", description="",
                 hashtags=["#gta6", " ", "GTAVI"]),
        ClipIdea(start_s=10, end_s=15, potential=50, reason="", title="short", description="",
                 hashtags=[]),
        ClipIdea(start_s=100, end_s=400, potential=50, reason="", title="long", description="",
                 hashtags=[]),
    ]  # fmt: skip
    out = sanitize(ideas, duration=300)
    assert [c.title for c in out] == ["a", "long"]
    assert out[0].start_s == 0 and out[0].potential == 100
    assert out[0].hashtags == ["gta6", "GTAVI"]
    assert out[1].end_s - out[1].start_s <= 75


def test_normalize_rms_finds_loud_second() -> None:
    rate = 100
    quiet = np.full(rate * 4, 10, dtype=np.float32)
    loud = np.full(rate, 1000, dtype=np.float32)
    energy = normalize_rms(np.concatenate([quiet, loud, quiet]), rate)
    assert energy.shape == (9,)
    assert energy.argmax() == 4


def test_heuristic_picks_loudest_window() -> None:
    energy = np.zeros(200)
    energy[120:160] = 1.0
    ideas = plan_heuristic("Video", [], energy, duration=200)
    assert ideas and ideas[0].start_s == 120


def test_cut_command_with_frame_and_encoder() -> None:
    cmd = build_cut_command(Path("in.mp4"), Path("out.mp4"), 10, 40, Path("f.png"), "libx264")
    joined = " ".join(cmd)
    assert cmd[cmd.index("-ss") + 1] == "10.00"
    assert cmd[cmd.index("-t") + 1] == "30.00"
    assert "[1:v]scale=1080:1920" in joined
    assert "libx264" in cmd
    no_frame = " ".join(build_cut_command(Path("a"), Path("b"), 0, 20, None, "h264_amf"))
    assert "[1:v]" not in no_frame and "h264_amf" in no_frame
