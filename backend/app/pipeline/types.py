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
