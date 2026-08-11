from __future__ import annotations

from datetime import timedelta

import pytest

from daylens.session_tracker import SessionTracker


class MappingClassifier:
    _MAPPING = {
        "Code.exe": ("coding", "Coding", "interactive_required"),
        "Chat.exe": ("social", "Social", "passive_allowed"),
        "Forum.exe": ("social", "Forum", "interactive_required"),
        "VLC.exe": ("video", "Video", "passive_allowed"),
    }

    def classify(self, process_name, _window_title):
        category_key, category_name, active_rule = self._MAPPING[process_name]
        return {
            "category_key": category_key,
            "category_name": category_name,
            "active_rule": active_rule,
        }


class VersionedMappingClassifier(MappingClassifier):
    classification_version = "rules-0123456789ab"


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


def test_flush_exception_still_advances_monotonic_deadline():
    clock = ManualClock()
    attempts = []

    def failing_flush(session):
        attempts.append(session)
        raise OSError("database busy")

    tracker = _tracker(
        on_flush=failing_flush,
        monotonic_clock=clock,
    )
    window = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 15,
    }
    clock.now = 5.0

    with pytest.raises(OSError, match="database busy"):
        tracker.tick(0, window)

    clock.now = 5.1
    tracker.tick(0, window)
    assert len(attempts) == 1

    clock.now = 10.0
    with pytest.raises(OSError, match="database busy"):
        tracker.tick(0, window)
    assert len(attempts) == 2


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


def test_new_session_uses_classifier_version_and_metric_default():
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=VersionedMappingClassifier(),
    )

    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 24,
        },
    )

    assert tracker.classification_version == "rules-0123456789ab"
    assert tracker.current_session.classification_version == "rules-0123456789ab"
    assert tracker.current_session.metric_version == "attention-v1"


def test_new_session_falls_back_to_legacy_classification_version():
    tracker = _tracker()

    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 25,
        },
    )

    assert tracker.classification_version == "legacy"
    assert tracker.current_session.classification_version == "legacy"


@pytest.mark.parametrize(
    ("target_process", "target_title"),
    [("VLC.exe", "Movie"), ("Chat.exe", "Friends")],
)
def test_cross_domain_session_uses_classifier_version(target_process, target_title):
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "cross_group_grace_seconds": 0,
                "min_session_seconds": 1,
            }
        },
        classifier=VersionedMappingClassifier(),
        on_session_end=lambda _session: True,
    )
    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 26,
        },
    )

    tracker.tick(
        0,
        {
            "process_name": target_process,
            "window_title": target_title,
            "exe_path": "",
            "pid": 27,
        },
    )
    if target_process == "Chat.exe":
        tracker.tick(
            0,
            {
                "process_name": target_process,
                "window_title": target_title,
                "exe_path": "",
                "pid": 27,
            },
        )

    assert tracker.current_session.process_name == target_process
    assert tracker.current_session.classification_version == "rules-0123456789ab"
    assert tracker.current_session.metric_version == "attention-v1"


def test_social_passive_grace_uses_pending_policy_at_threshold_boundary():
    tracker = _tracker(idle_threshold=1, passive_threshold=3)
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 30,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 31,
    }
    tracker.tick(0, coding)

    first = tracker.tick(0, social)
    boundary = tracker.tick(0, social)

    assert tracker.current_session.process_name == "Code.exe"
    assert tracker._pending_switch["domain"] == "social"
    assert tracker.cross_group_grace == 30
    assert tracker._pending_switch["effective_during_grace"] == 2
    assert tracker._pending_switch["idle_during_grace"] == 0
    assert first["is_effective"] is True
    assert boundary["is_effective"] is True

    tracker._pending_switch["since"] -= timedelta(seconds=31)
    after_threshold = tracker.tick(0, social)

    assert tracker.current_session.process_name == "Chat.exe"
    assert tracker.current_session.effective_seconds == 0
    assert tracker.current_session.idle_seconds == 3
    assert after_threshold["is_effective"] is False


def test_social_interactive_grace_uses_normal_threshold_and_matches_snapshot():
    tracker = _tracker(idle_threshold=2, passive_threshold=10)
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 32,
    }
    social = {
        "process_name": "Forum.exe",
        "window_title": "Forum",
        "exe_path": "",
        "pid": 33,
    }
    tracker.tick(0, coding)

    at_boundary = tracker.tick(0, social)
    assert at_boundary["is_effective"] is True
    assert tracker._pending_switch["effective_during_grace"] == 1

    tracker._pending_switch["since"] -= timedelta(seconds=31)
    after_threshold = tracker.tick(0, social)

    assert tracker.current_session.process_name == "Forum.exe"
    assert tracker.current_session.effective_seconds == 0
    assert tracker.current_session.idle_seconds == 2
    assert after_threshold["is_effective"] is False


def test_immediate_entertainment_switch_waits_when_end_callback_returns_false():
    callback_results = iter([False, True])
    callback_sessions = []

    def persist(session):
        callback_sessions.append(session)
        return next(callback_results)

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "cross_group_grace_seconds": 30,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=persist,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 34,
    }
    video = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 35,
    }
    tracker.tick(0, coding)
    original_session = tracker.current_session

    failed_snapshot = tracker.tick(0, video)

    assert tracker.current_session is original_session
    assert tracker.current_session.process_name == "Code.exe"
    assert tracker._pending_switch["domain"] == "entertainment"
    assert tracker._pending_switch["process_name"] == "VLC.exe"
    assert failed_snapshot["process_name"] == "VLC.exe"
    assert failed_snapshot["category_key"] == "video"
    assert len(callback_sessions) == 1

    tracker.tick(0, video)

    assert tracker.current_session is not original_session
    assert tracker.current_session.process_name == "VLC.exe"
    assert tracker._pending_switch is None
    assert len(callback_sessions) == 2


def test_pending_video_with_audio_stays_effective_past_passive_threshold():
    persist_attempts = []

    def persist(session):
        persist_attempts.append(session)
        return len(persist_attempts) > 303

    audio = AudioForPid(playing_pid=51)
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "entertainment_idle_threshold_seconds": 300,
                "cross_group_grace_seconds": 30,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=persist,
        audio_detector=audio,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 50,
    }
    video = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 51,
    }
    tracker.tick(0, coding)

    for _ in range(303):
        failed_snapshot = tracker.tick(0, video)

    pending = tracker._pending_switch
    assert pending["pid"] == 51
    assert pending["effective_during_grace"] == 303
    assert pending["idle_during_grace"] == 0
    assert failed_snapshot["audio_playing"] is True
    assert failed_snapshot["is_effective"] is True

    success_snapshot = tracker.tick(0, video)
    session = tracker.current_session

    assert len(persist_attempts) == 304
    assert session.process_name == "VLC.exe"
    assert session.duration_seconds == 304
    assert session.effective_seconds == 304
    assert session.idle_seconds == 0
    assert session.duration_seconds == (
        session.effective_seconds + session.idle_seconds
    )
    assert success_snapshot["audio_playing"] is True
    assert success_snapshot["is_effective"] is True
    assert set(audio.seen_pids) == {51}


def test_immediate_entertainment_switch_conserves_abandoned_grace_counters():
    ended = []
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "cross_group_grace_seconds": 30,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=ended.append,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 40,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 41,
    }
    video = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 42,
    }
    tracker.tick(0, coding)
    tracker.tick(0, social)
    tracker.tick(0, social)
    pending_seconds = (
        tracker._pending_switch["effective_during_grace"]
        + tracker._pending_switch["idle_during_grace"]
    )
    old_duration = tracker.current_session.duration_seconds

    tracker.tick(0, video)

    assert len(ended) == 1
    assert ended[0].duration_seconds == old_duration + pending_seconds
    assert (
        ended[0].effective_seconds + ended[0].idle_seconds
        == ended[0].duration_seconds
    )
    assert tracker.current_session.process_name == "VLC.exe"
    assert tracker._pending_switch is None


def test_grace_confirmation_waits_when_end_callback_returns_false():
    callback_results = iter([False, True])
    callback_sessions = []

    def persist(session):
        callback_sessions.append(session)
        return next(callback_results)

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "cross_group_grace_seconds": 30,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=persist,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 36,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 37,
    }
    tracker.tick(0, coding)
    original_session = tracker.current_session
    tracker.tick(0, social)
    tracker._pending_switch["since"] -= timedelta(seconds=31)

    tracker.tick(0, social)

    assert tracker.current_session is original_session
    assert tracker._pending_switch is not None
    assert len(callback_sessions) == 1

    tracker.tick(0, social)

    assert tracker.current_session is not original_session
    assert tracker.current_session.process_name == "Chat.exe"
    assert tracker._pending_switch is None
    assert len(callback_sessions) == 2
