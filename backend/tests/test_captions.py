import pytest
from pydantic import ValidationError

from app.pipeline import captions
from app.pipeline.captions import CaptionStyle
from app.pipeline.cut import build_cut_command
from app.pipeline.types import Word


def w(start: float, end: float, word: str) -> Word:
    return Word(start=start, end=end, word=word)


def test_ass_color_and_time() -> None:
    assert captions.ass_color("#FFE14D") == "&H004DE1FF"
    assert captions.ass_time(3725.456) == "1:02:05.46"
    assert captions.ass_time(-1) == "0:00:00.00"


def test_clip_words_shifts_trims_and_cleans() -> None:
    words = [w(9, 10.2, "antes"), w(10.5, 11, "{oi}"), w(11, 11.5, " \\ "), w(29.8, 31, "fim")]
    out = captions.clip_words(words, 10, 30)
    assert [x["word"] for x in out] == ["antes", "oi", "fim"]
    assert out[0]["start"] == 0 and out[0]["end"] == pytest.approx(0.2)
    assert out[-1]["end"] == pytest.approx(20)  # cut at the clip end


def test_chunks_break_on_size_pause_and_sentence_end() -> None:
    words = [w(0, 0.3, "um"), w(0.3, 0.6, "dois"), w(0.6, 0.9, "três"), w(0.9, 1.2, "quatro."),
             w(1.2, 1.5, "cinco"), w(3, 3.3, "seis")]  # fmt: skip
    chunks = captions.chunk_words(words, max_words=3)
    assert [[x["word"] for x in c] for c in chunks] == [
        ["um", "dois", "três"],
        ["quatro."],
        ["cinco"],
        ["seis"],
    ]


def test_build_ass_highlights_one_word_per_event() -> None:
    style = CaptionStyle(max_words=2, uppercase=True, position_y=0.5)
    ass = captions.build_ass([w(0, 0.4, "olá"), w(0.5, 1, "mundo")], 5, style)
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    assert len(events) == 2
    hi = captions.ass_color(style.highlight)
    assert events[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.50,")
    assert f"{{\\pos(540,960)}}{{\\c{hi}\\fscx112\\fscy112}}OLÁ{{\\r}} MUNDO" in events[0]
    assert events[1].endswith(f"OLÁ {{\\c{hi}\\fscx112\\fscy112}}MUNDO{{\\r}}")
    assert ",0:00:01.30," in events[1]  # held a bit after the last word
    assert "Style: Cap,Arial Black,84," in ass


def test_style_validation() -> None:
    with pytest.raises(ValidationError):
        CaptionStyle(color="white")
    with pytest.raises(ValidationError):
        CaptionStyle(font="Comic Sans MS")  # type: ignore[arg-type]


def test_cut_command_burns_captions_after_frame(tmp_path) -> None:  # noqa: ANN001
    cmd = build_cut_command(
        tmp_path / "a.mp4", tmp_path / "b.mp4", 1, 5, tmp_path / "f.png", "libx264",
        subtitles="captions.ass",
    )  # fmt: skip
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert graph.index("[base][fr]overlay") < graph.index("ass=captions.ass")
    assert graph.endswith("ass=captions.ass,format=yuv420p[v]")
