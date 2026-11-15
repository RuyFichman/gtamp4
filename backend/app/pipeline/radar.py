"""Find new YouTube videos for the Radar (search terms and channels) without downloading."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote_plus

import yt_dlp

from app.pipeline.download import BASE_OPTS, canonical_url

PER_QUERY = 15
MIN_DURATION_S = 90  # shorter is already a short; nothing to cut
MAX_DURATION_S = 3 * 3600  # hours-long streams are too slow to process

_CHANNEL_ID = re.compile(r"^UC[\w-]{22}$")

# flat listings only say "há 9 horas"; this makes yt-dlp turn it into an (approximate) timestamp
LIST_OPTS: dict[str, Any] = {
    **BASE_OPTS,
    "extract_flat": "in_playlist",
    "extractor_args": {"youtubetab": {"approximate_date": [""]}},
}


@dataclass
class Found:
    youtube_id: str
    url: str
    title: str
    channel: str
    duration_s: float | None
    views: int | None
    channel_id: str | None = None
    published_at: datetime | None = None  # approximate (hour/day granularity)
    subscribers: int | None = None  # only on channel listings; search results don't carry it


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


def _published(entry: dict[str, Any]) -> datetime | None:
    ts = entry.get("timestamp") or entry.get("release_timestamp")
    return datetime.fromtimestamp(ts, UTC) if isinstance(ts, int | float) else None


def parse_entries(info: dict[str, Any]) -> list[Found]:
    playlist_channel = info.get("channel") or info.get("uploader") or ""
    playlist_channel_id = info.get("channel_id")
    playlist_subs = info.get("channel_follower_count")  # set on channel listings
    found = []
    for e in info.get("entries") or []:
        if not e or not e.get("id") or e.get("ie_key", "Youtube") != "Youtube":
            continue
        channel_id = e.get("channel_id") or playlist_channel_id
        found.append(
            Found(
                youtube_id=e["id"],
                url=canonical_url(e["id"]),
                title=e.get("title") or "",
                channel=e.get("channel") or e.get("uploader") or playlist_channel,
                duration_s=e.get("duration"),
                views=e.get("view_count"),
                channel_id=channel_id,
                published_at=_published(e),
                subscribers=playlist_subs
                if channel_id and channel_id == playlist_channel_id
                else None,
            )
        )
    return found


def list_videos(kind: str, query: str, limit: int = PER_QUERY) -> list[Found]:
    with yt_dlp.YoutubeDL({**LIST_OPTS, "playlistend": limit}) as ydl:
        info = ydl.extract_info(source_url(kind, query), download=False)
    return parse_entries(info or {})[:limit]


def channel_subscribers(channel_id: str) -> int | None:
    """Subscriber count from the channel page (one quick request, nothing downloaded).
    None when the channel hides it."""
    with yt_dlp.YoutubeDL({**LIST_OPTS, "playlistend": 1}) as ydl:
        info = ydl.extract_info(channel_url(channel_id), download=False)
    subs = (info or {}).get("channel_follower_count")
    return int(subs) if isinstance(subs, int | float) else None


def prefilter(video: Found) -> str | None:
    """Cheap checks before spending AI. Returns the rejection reason, or None to keep."""
    if video.duration_s is None:
        return "Ao vivo ou sem duração"
    if video.duration_s < MIN_DURATION_S:
        return "Curto demais (já é um short)"
    if video.duration_s > MAX_DURATION_S:
        return "Longo demais (live de horas)"
    return None
