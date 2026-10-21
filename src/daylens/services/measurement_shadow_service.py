"""Privacy-safe aggregate shadow telemetry for measurement-policy review."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

from ..measurement import PlaybackEvidence, SampleIntervalObservation, sample_ratio_bucket
from .intelligence_state import atomic_json


def _empty_state(now: datetime) -> dict:
    return {
        "version": 1,
        "updated_at": now.isoformat(timespec="seconds"),
        "samples": {
            "count": 0,
            "sum_elapsed_seconds": 0.0,
            "max_elapsed_seconds": 0.0,
            "wall_clock_rollbacks": 0,
            "ratio_buckets": {
                "le_1_25x": 0,
                "le_2x": 0,
                "le_5x": 0,
                "gt_5x": 0,
            },
        },
        "playback": {"count": 0, "states": {}, "sources": {}},
    }


class MeasurementShadowRecorder:
    """Accumulate only numeric/source aggregates; never activity identity."""

    def __init__(self, path, *, flush_every=60, now=datetime.now):
        self.path = Path(path)
        self._flush_every = max(1, int(flush_every))
        self._now = now
        self._lock = threading.Lock()
        self._dirty = 0
        self._state = self._load()

    def _load(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") == 1:
                return payload
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return _empty_state(self._now())

    def record_sample(self, observation: SampleIntervalObservation | None) -> None:
        if observation is None:
            return
        with self._lock:
            samples = self._state["samples"]
            samples["count"] += 1
            samples["sum_elapsed_seconds"] = round(
                samples["sum_elapsed_seconds"] + observation.elapsed_seconds, 6
            )
            samples["max_elapsed_seconds"] = max(
                samples["max_elapsed_seconds"], observation.elapsed_seconds
            )
            samples["wall_clock_rollbacks"] += int(observation.wall_clock_rollback)
            samples["ratio_buckets"][sample_ratio_bucket(observation.ratio)] += 1
            self._mark_dirty_locked()

    def record_playback(self, evidence: PlaybackEvidence | None) -> None:
        if evidence is None:
            return
        with self._lock:
            playback = self._state["playback"]
            playback["count"] += 1
            state = evidence.state.value
            playback["states"][state] = playback["states"].get(state, 0) + 1
            source = str(evidence.source)[:60]
            playback["sources"][source] = playback["sources"].get(source, 0) + 1
            self._mark_dirty_locked()

    def _mark_dirty_locked(self) -> None:
        self._dirty += 1
        if self._dirty >= self._flush_every:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self._dirty:
            return
        self._state["updated_at"] = self._now().isoformat(timespec="seconds")
        atomic_json(self.path, self._state)
        self._dirty = 0

    def close(self) -> None:
        with self._lock:
            self._flush_locked()
