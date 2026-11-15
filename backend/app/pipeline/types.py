from typing import TypedDict


class Segment(TypedDict):
    start: float
    end: float
    text: str


class Word(TypedDict):
    """One spoken word with its timing (seconds), for burned-in captions."""

    start: float
    end: float
    word: str


class HeatPoint(TypedDict):
    """One slice of YouTube's "most replayed" graph; value is 0..1 (1 = most replayed)."""

    start: float
    end: float
    value: float


class Chapter(TypedDict):
    start: float
    end: float
    title: str
