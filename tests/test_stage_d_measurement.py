import json
from datetime import datetime, timedelta

from daylens.measurement import (
    PlaybackEvidence,
    PlaybackState,
    observe_sample_interval,
)
from daylens.services.measurement_shadow_service import MeasurementShadowRecorder


def test_sample_observation_uses_monotonic_elapsed_and_flags_wall_rollback():
    prior = datetime(2026, 10, 20, 10, 0, 1)
    current = prior - timedelta(seconds=30)

    observation = observe_sample_interval(
        previous_monotonic=100.0,
        current_monotonic=101.4,
        previous_wall=prior,
        current_wall=current,
        expected_seconds=1.0,
    )

    assert observation.elapsed_seconds == 1.4
    assert observation.wall_elapsed_seconds == -30.0
    assert observation.wall_clock_rollback is True
    assert observation.ratio == 1.4


def test_first_sample_has_no_elapsed_observation():
    assert observe_sample_interval(
        previous_monotonic=None,
        current_monotonic=10.0,
        previous_wall=None,
        current_wall=datetime(2026, 10, 20, 10, 0),
        expected_seconds=1.0,
    ) is None


def test_shadow_recorder_persists_only_bounded_aggregate_evidence(tmp_path):
    path = tmp_path / "measurement-shadow.json"
    recorder = MeasurementShadowRecorder(path, flush_every=1, now=lambda: datetime(2026, 10, 20, 10, 0))
    first = datetime(2026, 10, 20, 9, 59, 59)
    for elapsed in (0.8, 1.1, 2.4, 7.0):
        recorder.record_sample(observe_sample_interval(
            previous_monotonic=10.0,
            current_monotonic=10.0 + elapsed,
            previous_wall=first,
            current_wall=first + timedelta(seconds=elapsed),
            expected_seconds=1.0,
        ))
    recorder.record_playback(PlaybackEvidence(
        state=PlaybackState.UNKNOWN,
        source="audio_query_error",
        observed_monotonic=12.0,
        valid_for_seconds=3.0,
        compatibility_playing=True,
    ))
    recorder.close()

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["samples"]["count"] == 4
    assert payload["samples"]["max_elapsed_seconds"] == 7.0
    assert sum(payload["samples"]["ratio_buckets"].values()) == 4
    assert payload["playback"]["states"]["unknown"] == 1
    assert payload["playback"]["sources"]["audio_query_error"] == 1
    serialized = json.dumps(payload, ensure_ascii=False)
    for private_value in ("title", "process", "pid", "url", "path"):
        assert private_value not in serialized.casefold()
