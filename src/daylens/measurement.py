"""Pure evidence models for sampling and media playback.

These models deliberately do not decide accounting policy.  They preserve the
raw observation needed to choose that policy from replay data later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PlaybackState(str, Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlaybackEvidence:
    state: PlaybackState
    source: str
    observed_monotonic: float
    valid_for_seconds: float
    compatibility_playing: bool

    def is_fresh(self, monotonic_now: float) -> bool:
        return monotonic_now - self.observed_monotonic < self.valid_for_seconds


@dataclass(frozen=True)
class SampleIntervalObservation:
    expected_seconds: float
    elapsed_seconds: float
    wall_elapsed_seconds: float
    wall_clock_rollback: bool

    @property
    def ratio(self) -> float:
        return self.elapsed_seconds / self.expected_seconds


def observe_sample_interval(
    *,
    previous_monotonic: float | None,
    current_monotonic: float,
    previous_wall: datetime | None,
    current_wall: datetime,
    expected_seconds: float,
) -> SampleIntervalObservation | None:
    """Return a raw interval observation using monotonic time as authority."""

    if previous_monotonic is None or previous_wall is None:
        return None
    expected = max(0.001, float(expected_seconds))
    elapsed = max(0.0, float(current_monotonic) - float(previous_monotonic))
    wall_elapsed = (current_wall - previous_wall).total_seconds()
    return SampleIntervalObservation(
        expected_seconds=expected,
        elapsed_seconds=round(elapsed, 6),
        wall_elapsed_seconds=round(wall_elapsed, 6),
        wall_clock_rollback=wall_elapsed < 0,
    )


def sample_ratio_bucket(ratio: float) -> str:
    """Bucket raw cadence ratios for diagnostics, not accounting decisions."""

    if ratio <= 1.25:
        return "le_1_25x"
    if ratio <= 2.0:
        return "le_2x"
    if ratio <= 5.0:
        return "le_5x"
    return "gt_5x"
