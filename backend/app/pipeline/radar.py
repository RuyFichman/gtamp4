"""Find new YouTube videos for the Radar (search terms and channels) without downloading."""

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import yt_dlp

from app.pipeline.download import BASE_OPTS, canonical_url

PER_QUERY = 15
MIN_DURATION_S = 90  # shorter is already a short; nothing to cut
MAX_DURATION_S = 3 * 3600  # hours-long streams are too slow to process

_CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")


@dataclass
class Found:
    youtube_id: str
    url: str
    title: str
    channel: str
    duration_s: float | None
    views: int | None


def search_url(term: str) -> str:
    # sp=CAI%3D sorts results by upload date (newest first)
    return f"https://www.youtube.com/results?search_query={quote_plus(term)}&sp=CAI%3D"


def channel_url(value: str) -> str:
    """Accepts @handle, a channel id (UC...) or any channel URL."""
    value = value.strip()
    if value.startswith("http"):
        base = value.rstrip("/")
        return base if base.endswith("/videos") else f"{base}/videos"
    if _CHANNEL_ID.match(value):
        return f"https://www.youtube.com/channel/{value}/videos"
    return f"https://www.youtube.com/@{value.lstrip('@')}/videos"


def source_url(kind: str, query: str) -> str:
    return channel_url(query) if kind == "channel" else search_url(query)


def parse_entries(info: dict[str, Any]) -> list[Found]:
    playlist_channel = info.get("channel") or info.get("uploader") or ""
    found = []
    for e in info.get("entries") or []:
        if not e or not e.get("id") or e.get("ie_key", "Youtube") != "Youtube":
            continue
        found.append(
            Found(
                youtube_id=e["id"],
                url=canonical_url(e["id"]),
                title=e.get("title") or "",
                channel=e.get("channel") or e.get("uploader") or playlist_channel,
                duration_s=e.get("duration"),
                views=e.get("view_count"),
            )
        )
    return found


def list_videos(kind: str, query: str, limit: int = PER_QUERY) -> list[Found]:
    opts = {**BASE_OPTS, "extract_flat": "in_playlist", "playlistend": limit}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source_url(kind, query), download=False)
    return parse_entries(info or {})[:limit]


def prefilter(video: Found) -> str | None:
    """Cheap checks before spending AI. Returns the rejection reason, or None to keep."""
    if video.duration_s is None:
        return "Ao vivo ou sem duração"
    if video.duration_s < MIN_DURATION_S:
        return "Curto demais (já é um short)"
    if video.duration_s > MAX_DURATION_S:
        return "Longo demais (live de horas)"
    return None
