"""Loudness per second of the whole audio track: voice AND game (gunfire, engines, music).
The AI gets it as "energia"; on gameplay it only means a reaction when someone talks there."""

import subprocess
from pathlib import Path

import numpy as np

SAMPLE_RATE = 8000


def loudness_per_second(video: Path) -> np.ndarray:
    """Returns one value per second, normalized to 0..1 (robust to outliers)."""
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
            "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-",
        ],
        capture_output=True,
    )  # fmt: skip
    if proc.returncode != 0:
        return np.zeros(0)
    samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
    return normalize_rms(samples, SAMPLE_RATE)


def normalize_rms(samples: np.ndarray, rate: int) -> np.ndarray:
    seconds = len(samples) // rate
    if seconds == 0:
        return np.zeros(0)
    frames = samples[: seconds * rate].reshape(seconds, rate)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    lo, hi = np.percentile(rms, 5), np.percentile(rms, 95)
    if hi - lo < 1e-6:
        return np.zeros(seconds)
    return np.clip((rms - lo) / (hi - lo), 0.0, 1.0)


def mean_between(energy: np.ndarray, start: float, end: float) -> float:
    window = energy[int(start) : max(int(start) + 1, int(end))]
    return float(window.mean()) if window.size else 0.0
