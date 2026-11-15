"""Which Radar video to cut first: how fast it is getting views for its channel's size, times
how the editor has judged that channel's clips so far.

Speed beats total views: 50k views in 6 h on a 20k-subscriber channel is a hotter topic than
200k in a week on a 2M channel. Dividing by the square root of the subscribers (instead of the
subscribers) sits between "absolute speed" (big channels always win) and "views per
subscriber" (any tiny channel with a few hundred views would win).
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime

MIN_AGE_H = 1.0  # "há 10 minutos" is too noisy to divide by
UNKNOWN_AGE_H = 48.0  # no publish time (old candidates): assume two days
SUBS_FLOOR = 10_000  # below this, the channel counts as 10k
SUBS_UNKNOWN = 100_000  # hidden subscriber count: treat as a mid-size channel

HISTORY_PRIOR = 5  # a channel's record counts like this many "average" decisions until it grows
WEIGHT_MIN, WEIGHT_MAX = 0.25, 3.0
BAD_CHANNEL_MIN_DECIDED = 6  # heuristic triage drops channels with at least this many
BAD_CHANNEL_MAX_RATE = 0.15  # decided clips and an approval rate this low


def channel_key(name: str) -> str:
    """Same channel in the Radar (search listing) and in SourceVideo (full metadata)."""
    return re.sub(r"\s+", " ", name).strip().casefold()


def views_per_hour(views: int | None, published_at: datetime | None, at: datetime) -> float:
    if not views:
        return 0.0
    hours = UNKNOWN_AGE_H if published_at is None else (at - published_at).total_seconds() / 3600
    return views / max(hours, MIN_AGE_H)


def heat(speed: float, subscribers: int | None) -> float:
    """Views per hour adjusted to the channel size."""
    subs = SUBS_UNKNOWN if subscribers is None else max(subscribers, SUBS_FLOOR)
    return speed / math.sqrt(subs)


@dataclass(frozen=True)
class ChannelRecord:
    """The editor's decisions on clips from one channel (approved includes posted)."""

    approved: int = 0
    rejected: int = 0

    @property
    def decided(self) -> int:
        return self.approved + self.rejected


@dataclass(frozen=True)
class ChannelHistory:
    records: dict[str, ChannelRecord] = field(default_factory=dict)  # by channel_key
    overall_rate: float | None = None  # approved / decided over every channel

    def of(self, channel: str) -> ChannelRecord | None:
        return self.records.get(channel_key(channel))


def channel_weight(record: ChannelRecord | None, overall_rate: float | None) -> float:
    """1.0 for unknown channels; up to 3x for channels whose clips keep getting approved, down
    to 0.25x for channels whose clips keep getting rejected. Few decisions barely move it
    (smoothed toward the overall approval rate)."""
    if record is None or record.decided == 0 or not overall_rate:
        return 1.0
    smoothed = (record.approved + HISTORY_PRIOR * overall_rate) / (record.decided + HISTORY_PRIOR)
    return min(max((smoothed / overall_rate) ** 2, WEIGHT_MIN), WEIGHT_MAX)


def is_bad_channel(record: ChannelRecord | None) -> bool:
    return (
        record is not None
        and record.decided >= BAD_CHANNEL_MIN_DECIDED
        and record.approved / record.decided <= BAD_CHANNEL_MAX_RATE
    )


def score(speed: float, subscribers: int | None, channel: str, history: ChannelHistory) -> float:
    return heat(speed, subscribers) * channel_weight(history.of(channel), history.overall_rate)
