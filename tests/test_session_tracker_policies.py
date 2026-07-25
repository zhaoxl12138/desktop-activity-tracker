from __future__ import annotations

import pytest

from daylens.session_tracker import SessionTracker


class MappingClassifier:
    _MAPPING = {
        "Code.exe": ("coding", "Coding", "interactive_required"),
        "Chat.exe": ("social", "Social", "passive_allowed"),
        "VLC.exe": ("video", "Video", "passive_allowed"),
    }

    def classify(self, process_name, _window_title):
        category_key, category_name, active_rule = self._MAPPING[process_name]
        return {
            "category_key": category_key,
            "category_name": category_name,
            "active_rule": active_rule,
        }


class ManualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class AudioForPid:
    def __init__(self, playing_pid):
        self.playing_pid = playing_pid
        self.seen_pids = []

    def is_playing(self, pid):
        self.seen_pids.append(pid)
        return pid == self.playing_pid


@pytest.fixture(autouse=True)
def stable_input(monkeypatch):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr(
        "daylens.session_tracker._get_keyboard_snapshot",
        lambda: bytes(256),
    )


def _tracker(
    *,
    sample_interval=1,
    idle_threshold=1,
    passive_threshold=3,
    on_flush=None,
    monotonic_clock=None,
    audio_detector=None,
):
    kwargs = {}
    if monotonic_clock is not None:
        kwargs["monotonic_clock"] = monotonic_clock
    return SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": sample_interval,
                "flush_interval_seconds": 5,
                "idle_threshold_seconds": idle_threshold,
                "entertainment_idle_threshold_seconds": passive_threshold,
                "min_session_seconds": 1,
            }
        },
        classifier=MappingClassifier(),
        on_flush=on_flush,
        audio_detector=audio_detector,
        **kwargs,
    )


def test_social_passive_rule_uses_passive_threshold_in_session_and_snapshot():
    tracker = _tracker()
    window = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 10,
    }

    tracker.tick(0, window)
    snapshot = tracker.tick(10, window)

    assert tracker.current_session.effective_seconds == 2
    assert tracker.current_session.idle_seconds == 0
    assert snapshot["is_effective"] is True
    assert snapshot["is_user_active"] is True


def test_interactive_rule_still_uses_normal_idle_threshold():
    tracker = _tracker()
    window = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 11,
    }

    tracker.tick(0, window)
    snapshot = tracker.tick(10, window)

    assert tracker.current_session.effective_seconds == 0
    assert tracker.current_session.idle_seconds == 2
    assert snapshot["is_effective"] is False
    assert snapshot["is_user_active"] is False


@pytest.mark.parametrize("sample_interval", [0.25, 2])
def test_flush_interval_uses_monotonic_seconds_not_tick_count(sample_interval):
    clock = ManualClock()
    flushed = []
    tracker = _tracker(
        sample_interval=sample_interval,
        on_flush=flushed.append,
        monotonic_clock=clock,
    )
    window = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 12,
    }

    for _ in range(6):
        tracker.tick(0, window)
    assert flushed == []

    clock.now = 4.9
    tracker.tick(0, window)
    assert flushed == []

    clock.now = 5.0
    tracker.tick(0, window)
    assert flushed == [tracker.current_session]


def test_immediate_work_to_video_switch_counts_the_new_sessions_first_sample():
    tracker = _tracker(sample_interval=2)
    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 13,
        },
    )

    snapshot = tracker.tick(
        0,
        {
            "process_name": "VLC.exe",
            "window_title": "Movie",
            "exe_path": "",
            "pid": 14,
        },
    )

    assert tracker.current_session.process_name == "VLC.exe"
    assert tracker.current_session.duration_seconds == 2
    assert tracker.current_session.effective_seconds == 2
    assert snapshot["duration_seconds"] == 2


def test_same_process_with_new_pid_refreshes_audio_detection_target():
    audio = AudioForPid(playing_pid=22)
    tracker = _tracker(audio_detector=audio)
    window = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "C:/VLC.exe",
        "pid": 21,
    }
    tracker.tick(0, window)

    window["pid"] = 22
    snapshot = tracker.tick(0, window)

    assert audio.seen_pids[-1] == 22
    assert snapshot["audio_playing"] is True


def test_finished_short_session_is_handed_to_persistence_callback():
    ended = []
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "flush_interval_seconds": 5,
                "idle_threshold_seconds": 60,
                "min_session_seconds": 2,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=ended.append,
    )
    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "scratch.py",
            "exe_path": "",
            "pid": 23,
        },
    )

    tracker.finish_current("shutdown")

    assert len(ended) == 1
    assert ended[0].duration_seconds == 1
    assert ended[0].switch_reason == "shutdown"
