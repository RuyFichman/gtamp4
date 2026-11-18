"""YouTube access through yt-dlp: metadata, video file, original-language subtitles, views."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yt_dlp

from app.config import get_settings
from app.pipeline.types import Chapter, HeatPoint

YOUTUBE_ID = re.compile(r"(?:v=|youtu\.be/|shorts/|live/|embed/)([A-Za-z0-9_-]{11})")

BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "js_runtimes": {"node": {}},
}


def parse_cookies_browser(value: str) -> tuple[str, str | None] | None:
    """'firefox' or 'firefox:profile' (from YTDLP_COOKIES_FROM_BROWSER) -> (browser, profile)."""
    value = value.strip()
    if not value:
        return None
    browser, _, profile = value.partition(":")
    return browser.strip().lower(), (profile.strip() or None)


def login_opts() -> dict[str, Any]:
    """BASE_OPTS plus the logged-in browser's cookies, when configured (age-restricted videos).
    Only downloads use it; Radar listings stay anonymous to spare the account."""
    parsed = parse_cookies_browser(get_settings().ytdlp_cookies_from_browser)
    if parsed is None:
        return dict(BASE_OPTS)
    browser, profile = parsed
    return {**BASE_OPTS, "cookiesfrombrowser": (browser, profile, None, None)}


def parse_youtube_id(url: str) -> str | None:
    match = YOUTUBE_ID.search(url)
    return match.group(1) if match else None


def canonical_url(youtube_id: str) -> str:
    return f"https://www.youtube.com/watch?v={youtube_id}"


@dataclass
class VideoInfo:
    youtube_id: str
    title: str
    channel: str
    description: str
    duration_s: float | None
    views: int | None
    language: str | None
    subtitle_json3: dict[str, Any] | None = field(default=None, repr=False)
    heatmap: list[HeatPoint] = field(default_factory=list, repr=False)
    chapters: list[Chapter] = field(default_factory=list)


def parse_heatmap(info: dict[str, Any]) -> list[HeatPoint]:
    """YouTube's "most replayed" graph (only on videos YouTube shows it for)."""
    out: list[HeatPoint] = []
    for h in info.get("heatmap") or []:
        try:
            out.append(
                HeatPoint(
                    start=round(float(h["start_time"]), 2),
                    end=round(float(h["end_time"]), 2),
                    value=round(float(h["value"]), 3),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def parse_chapters(info: dict[str, Any]) -> list[Chapter]:
    out: list[Chapter] = []
    for c in info.get("chapters") or []:
        try:
            start, end = float(c["start_time"]), float(c["end_time"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(Chapter(start=round(start, 2), end=round(end, 2), title=str(c.get("title", ""))))
    return out


def _original_language(info: dict[str, Any]) -> str | None:
    if info.get("language"):
        return str(info["language"]).split("-")[0]
    for key in info.get("automatic_captions") or {}:
        if key.endswith("-orig"):
            return key.removesuffix("-orig").split("-")[0]
    return None


def _pick_subtitle_url(info: dict[str, Any], lang: str | None) -> str | None:
    """Manual subs in the original language > auto '-orig' > auto in lang. Never a translation."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    candidates: list[list[dict[str, Any]]] = []
    if lang:
        candidates += [manual.get(k, []) for k in manual if k.split("-")[0] == lang]
        candidates.append(auto.get(f"{lang}-orig", []))
        candidates.append(auto.get(lang, []))
    elif len(manual) == 1:
        candidates.append(next(iter(manual.values())))
    for tracks in candidates:
        for track in tracks:
            if track.get("ext") == "json3" and track.get("url"):
                return str(track["url"])
    return None


def fetch_info(url: str) -> VideoInfo:
    with yt_dlp.YoutubeDL(login_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
        lang = _original_language(info)
        sub_url = _pick_subtitle_url(info, lang)
        subtitle = json.loads(ydl.urlopen(sub_url).read().decode("utf-8")) if sub_url else None
    return VideoInfo(
        youtube_id=info["id"],
        title=info.get("title") or "",
        channel=info.get("channel") or info.get("uploader") or "",
        description=info.get("description") or "",
        duration_s=info.get("duration"),
        views=info.get("view_count"),
        language=lang,
        subtitle_json3=subtitle,
        heatmap=parse_heatmap(info),
        chapters=parse_chapters(info),
    )


def download_video(url: str, dest_dir: Path, youtube_id: str) -> Path:
    target = dest_dir / f"{youtube_id}.mp4"
    if target.exists() and target.stat().st_size > 0:
        return target
    opts = {
        **login_opts(),
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    if not target.exists():
        raise RuntimeError(f"Download terminou mas o arquivo não foi encontrado: {target.name}")
    return target


def fetch_views(url: str) -> int | None:
    with yt_dlp.YoutubeDL(login_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    return info.get("view_count")
