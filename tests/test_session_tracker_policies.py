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


class ConfigurableVersionClassifier(MappingClassifier):
    def __init__(self, classification_version):
        self.classification_version = classification_version


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


def _assert_attention_conserved(session):
    assert session.duration_seconds == (
        session.engaged_seconds
        + session.passive_seconds
        + session.idle_seconds
    )
    assert session.effective_seconds == (
        session.engaged_seconds + session.passive_seconds
    )


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


def test_non_video_passive_rule_uses_normal_idle_threshold():
    tracker = _tracker()
    window = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 10,
    }

    tracker.tick(0, window)
    snapshot = tracker.tick(10, window)

    assert tracker.current_session.engaged_seconds == 0
    assert tracker.current_session.passive_seconds == 0
    assert tracker.current_session.effective_seconds == 0
    assert tracker.current_session.idle_seconds == 2
    assert snapshot["attention_state"] == "idle"
    assert snapshot["is_effective"] is False
    assert snapshot["is_user_active"] is False


def test_active_video_counts_as_engaged_and_snapshot_exposes_versions():
    tracker = _tracker(audio_detector=AudioForPid(playing_pid=9))
    window = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 9,
    }
    tracker.mark_user_active()

    snapshot = tracker.tick(0, window)
    session = tracker.current_session

    assert session.engaged_seconds == 1
    assert session.passive_seconds == 0
    assert session.idle_seconds == 0
    assert snapshot["engaged_seconds"] == 1
    assert snapshot["passive_seconds"] == 0
    assert snapshot["attention_state"] == "engaged"
    assert snapshot["metric_version"] == "attention-v1"
    assert snapshot["classification_version"] == "legacy"
    assert snapshot["is_effective"] is True
    _assert_attention_conserved(session)


def test_idle_video_with_audio_back_corrects_engaged_window_to_passive():
    tracker = _tracker(
        idle_threshold=1,
        passive_threshold=99,
        audio_detector=AudioForPid(playing_pid=10),
    )
    window = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 10,
    }

    tracker.tick(0, window)
    tracker.tick(0, window)
    snapshot = tracker.tick(0, window)
    session = tracker.current_session

    assert session.engaged_seconds == 0
    assert session.passive_seconds == 3
    assert session.idle_seconds == 0
    assert session.effective_seconds == 3
    assert tracker._persistent_idle == 3
    assert snapshot["attention_state"] == "passive"
    assert snapshot["is_effective"] is True
    _assert_attention_conserved(session)


def test_idle_video_without_audio_back_corrects_engaged_window_to_idle():
    tracker = _tracker(idle_threshold=1, passive_threshold=99)
    window = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 10,
    }

    tracker.tick(0, window)
    tracker.tick(0, window)
    snapshot = tracker.tick(0, window)
    session = tracker.current_session

    assert session.engaged_seconds == 0
    assert session.passive_seconds == 0
    assert session.idle_seconds == 3
    assert snapshot["attention_state"] == "idle"
    assert snapshot["is_effective"] is False
    _assert_attention_conserved(session)


def test_audio_from_non_video_process_never_counts_as_passive():
    tracker = _tracker(
        idle_threshold=1,
        audio_detector=AudioForPid(playing_pid=11),
    )
    window = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 11,
    }

    tracker.tick(0, window)
    tracker.tick(0, window)
    snapshot = tracker.tick(0, window)
    session = tracker.current_session

    assert session.engaged_seconds == 0
    assert session.passive_seconds == 0
    assert session.idle_seconds == 3
    assert snapshot["audio_playing"] is False
    assert snapshot["attention_state"] == "idle"
    _assert_attention_conserved(session)


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

    assert tracker.current_session.engaged_seconds == 0
    assert tracker.current_session.passive_seconds == 0
    assert tracker.current_session.effective_seconds == 0
    assert tracker.current_session.idle_seconds == 2
    assert snapshot["attention_state"] == "idle"
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

    tracker.mark_user_active()
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
    assert tracker.current_session.engaged_seconds == 2
    assert tracker.current_session.passive_seconds == 0
    assert tracker.current_session.effective_seconds == 2
    assert snapshot["duration_seconds"] == 2
    _assert_attention_conserved(tracker.current_session)


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


def test_classifier_version_change_closes_active_session_before_replacement():
    ended = []
    original_classifier = ConfigurableVersionClassifier("rules-old")
    replacement_classifier = ConfigurableVersionClassifier("rules-new")
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=original_classifier,
        on_session_end=lambda session: ended.append(session) or True,
    )
    window = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 28,
    }
    tracker.tick(0, window)
    old_session = tracker.current_session

    replaced = tracker.replace_classifier(replacement_classifier)

    assert replaced is True
    assert ended == [old_session]
    assert old_session.switch_reason == "classification_change"
    assert old_session.classification_version == "rules-old"
    assert tracker.current_session is None
    assert tracker.classifier is replacement_classifier
    assert tracker.classification_version == "rules-new"

    tracker.tick(0, window)

    assert tracker.current_session.session_id != old_session.session_id
    assert tracker.current_session.classification_version == "rules-new"


def test_same_classifier_version_keeps_active_and_pending_session_state():
    ended = []
    original_classifier = ConfigurableVersionClassifier("rules-same")
    replacement_classifier = ConfigurableVersionClassifier("rules-same")
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=original_classifier,
        on_session_end=lambda session: ended.append(session) or True,
    )
    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 29,
        },
    )
    tracker.tick(
        0,
        {
            "process_name": "Chat.exe",
            "window_title": "Friends",
            "exe_path": "",
            "pid": 30,
        },
    )
    old_session = tracker.current_session
    pending = tracker._pending_switch

    replaced = tracker.replace_classifier(replacement_classifier)

    assert replaced is True
    assert ended == []
    assert tracker.current_session is old_session
    assert tracker._pending_switch is pending
    assert tracker.classifier is replacement_classifier
    assert tracker.classification_version == "rules-same"


def test_classifier_version_change_preserves_and_clears_pending_counters():
    ended = []
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=ConfigurableVersionClassifier("rules-old"),
        on_session_end=lambda session: ended.append(session) or True,
    )
    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 31,
        },
    )
    tracker.tick(
        0,
        {
            "process_name": "Chat.exe",
            "window_title": "Friends",
            "exe_path": "",
            "pid": 32,
        },
    )
    expected_duration = tracker.current_session.duration_seconds + (
        tracker._pending_switch["engaged_during_grace"]
        + tracker._pending_switch["passive_during_grace"]
        + tracker._pending_switch["idle_during_grace"]
    )

    replaced = tracker.replace_classifier(
        ConfigurableVersionClassifier("rules-new")
    )

    assert replaced is True
    assert len(ended) == 1
    assert ended[0].duration_seconds == expected_duration
    _assert_attention_conserved(ended[0])
    assert tracker.current_session is None
    assert tracker._pending_switch is None
    assert tracker.classification_version == "rules-new"


def test_failed_classifier_boundary_keeps_old_version_and_pending_state():
    persist_results = iter([False, True])
    persist_attempts = []

    def persist(session):
        persist_attempts.append(session)
        return next(persist_results)

    original_classifier = ConfigurableVersionClassifier("rules-old")
    replacement_classifier = ConfigurableVersionClassifier("rules-new")
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=original_classifier,
        on_session_end=persist,
    )
    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 33,
        },
    )
    tracker.tick(
        0,
        {
            "process_name": "Chat.exe",
            "window_title": "Friends",
            "exe_path": "",
            "pid": 34,
        },
    )
    old_session = tracker.current_session
    old_end_time = old_session.end_time
    old_reason = old_session.switch_reason
    pending = tracker._pending_switch
    old_counters = (
        old_session.duration_seconds,
        old_session.engaged_seconds,
        old_session.passive_seconds,
        old_session.effective_seconds,
        old_session.idle_seconds,
    )

    replaced = tracker.replace_classifier(replacement_classifier)

    assert replaced is False
    assert tracker.current_session is old_session
    assert tracker._pending_switch is pending
    assert tracker.classifier is original_classifier
    assert tracker.classification_version == "rules-old"
    assert old_session.end_time == old_end_time
    assert old_session.switch_reason == old_reason
    assert (
        old_session.duration_seconds,
        old_session.engaged_seconds,
        old_session.passive_seconds,
        old_session.effective_seconds,
        old_session.idle_seconds,
    ) == old_counters

    assert tracker.replace_classifier(replacement_classifier) is True
    assert len(persist_attempts) == 2
    assert tracker.current_session is None
    assert tracker._pending_switch is None
    assert tracker.classification_version == "rules-new"


def test_classifier_boundary_exception_rolls_back_active_and_pending_state():
    def persist(_session):
        raise OSError("database busy")

    original_classifier = ConfigurableVersionClassifier("rules-old")
    replacement_classifier = ConfigurableVersionClassifier("rules-new")
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=original_classifier,
        on_session_end=persist,
    )
    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 35,
        },
    )
    tracker.tick(
        0,
        {
            "process_name": "Chat.exe",
            "window_title": "Friends",
            "exe_path": "",
            "pid": 36,
        },
    )
    old_session = tracker.current_session
    pending = tracker._pending_switch
    old_state = (
        old_session.end_time,
        old_session.switch_reason,
        old_session.duration_seconds,
        old_session.engaged_seconds,
        old_session.passive_seconds,
        old_session.effective_seconds,
        old_session.idle_seconds,
    )

    with pytest.raises(OSError, match="database busy"):
        tracker.replace_classifier(replacement_classifier)

    assert tracker.current_session is old_session
    assert tracker._pending_switch is pending
    assert tracker.classifier is original_classifier
    assert tracker.classification_version == "rules-old"
    assert (
        old_session.end_time,
        old_session.switch_reason,
        old_session.duration_seconds,
        old_session.engaged_seconds,
        old_session.passive_seconds,
        old_session.effective_seconds,
        old_session.idle_seconds,
    ) == old_state


def test_social_passive_grace_uses_normal_threshold_and_stays_non_passive():
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
    assert tracker._pending_switch["engaged_during_grace"] == 0
    assert tracker._pending_switch["passive_during_grace"] == 0
    assert tracker._pending_switch["idle_during_grace"] == 2
    assert first["is_effective"] is False
    assert boundary["is_effective"] is False

    tracker._pending_switch["since"] -= timedelta(seconds=31)
    after_threshold = tracker.tick(0, social)

    assert tracker.current_session.process_name == "Chat.exe"
    assert tracker.current_session.engaged_seconds == 0
    assert tracker.current_session.passive_seconds == 0
    assert tracker.current_session.effective_seconds == 0
    assert tracker.current_session.idle_seconds == 3
    assert after_threshold["is_effective"] is False
    _assert_attention_conserved(tracker.current_session)


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
    assert tracker._pending_switch["engaged_during_grace"] == 1
    assert tracker._pending_switch["passive_during_grace"] == 0

    tracker._pending_switch["since"] -= timedelta(seconds=31)
    after_threshold = tracker.tick(0, social)

    assert tracker.current_session.process_name == "Forum.exe"
    assert tracker.current_session.engaged_seconds == 0
    assert tracker.current_session.passive_seconds == 0
    assert tracker.current_session.effective_seconds == 0
    assert tracker.current_session.idle_seconds == 2
    assert after_threshold["is_effective"] is False
    _assert_attention_conserved(tracker.current_session)


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


def test_pending_video_with_audio_stays_passive_past_auto_close_threshold():
    persist_attempts = []

    def persist(session):
        persist_attempts.append(session)
        return len(persist_attempts) > 4

    audio = AudioForPid(playing_pid=51)
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
                "entertainment_idle_threshold_seconds": 3,
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

    for _ in range(4):
        failed_snapshot = tracker.tick(0, video)

    pending = tracker._pending_switch
    assert pending["pid"] == 51
    assert pending["engaged_during_grace"] == 0
    assert pending["passive_during_grace"] == 4
    assert pending["idle_during_grace"] == 0
    assert failed_snapshot["audio_playing"] is True
    assert failed_snapshot["is_effective"] is True

    success_snapshot = tracker.tick(0, video)
    session = tracker.current_session

    assert len(persist_attempts) == 5
    assert session.process_name == "VLC.exe"
    assert session.duration_seconds == 5
    assert session.engaged_seconds == 0
    assert session.passive_seconds == 5
    assert session.effective_seconds == 5
    assert session.idle_seconds == 0
    _assert_attention_conserved(session)
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
        tracker._pending_switch["engaged_during_grace"]
        + tracker._pending_switch["passive_during_grace"]
        + tracker._pending_switch["idle_during_grace"]
    )
    old_duration = tracker.current_session.duration_seconds

    tracker.tick(0, video)

    assert len(ended) == 1
    assert ended[0].duration_seconds == old_duration + pending_seconds
    _assert_attention_conserved(ended[0])
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
    _assert_attention_conserved(tracker.current_session)


def test_cancelled_grace_preserves_all_pending_attention_buckets():
    tracker = _tracker(idle_threshold=1, passive_threshold=99)
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 60,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 61,
    }
    tracker.tick(0, coding)
    tracker.tick(0, social)
    tracker.tick(0, social)
    pending_total = sum(
        tracker._pending_switch[key]
        for key in (
            "engaged_during_grace",
            "passive_during_grace",
            "idle_during_grace",
        )
    )
    before = tracker.current_session.duration_seconds

    tracker.mark_user_active()
    tracker.tick(0, coding)
    session = tracker.current_session

    assert tracker._pending_switch is None
    assert session.duration_seconds == before + pending_total + 1
    _assert_attention_conserved(session)


def test_finish_current_folds_pending_attention_once_when_persistence_retries():
    persist_results = iter([False, True])
    attempts = []

    def persist(session):
        attempts.append(
            (
                session.duration_seconds,
                session.engaged_seconds,
                session.passive_seconds,
                session.idle_seconds,
            )
        )
        return next(persist_results)

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
                "min_session_seconds": 1,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=persist,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 62,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 63,
    }
    tracker.tick(0, coding)
    tracker.tick(0, social)
    expected_duration = tracker.current_session.duration_seconds + sum(
        tracker._pending_switch[key]
        for key in (
            "engaged_during_grace",
            "passive_during_grace",
            "idle_during_grace",
        )
    )

    assert tracker.finish_current("shutdown") is False
    assert tracker.current_session is not None
    assert tracker._pending_switch is None
    assert tracker.current_session.duration_seconds == expected_duration
    _assert_attention_conserved(tracker.current_session)

    assert tracker.finish_current("shutdown") is True
    assert tracker.current_session is None
    assert attempts[0] == attempts[1]


@pytest.mark.parametrize("boundary", ["cross_day", "system_gap"])
def test_hard_boundary_preserves_pending_attention_counters(boundary):
    ended = []
    tracker = _tracker(idle_threshold=1, passive_threshold=99)
    tracker._on_session_end = ended.append
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 64,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 65,
    }
    tracker.tick(0, coding)
    tracker.tick(0, social)
    expected_duration = tracker.current_session.duration_seconds + sum(
        tracker._pending_switch[key]
        for key in (
            "engaged_during_grace",
            "passive_during_grace",
            "idle_during_grace",
        )
    )
    if boundary == "cross_day":
        tracker.current_session.date = "1999-01-01"
    else:
        tracker._last_tick_wall_time -= timedelta(seconds=600)

    tracker.tick(0, social)

    assert ended and ended[0].switch_reason == boundary
    assert ended[0].duration_seconds == expected_duration
    _assert_attention_conserved(ended[0])


def test_audible_video_is_not_auto_closed_and_silent_tail_does_not_erase_passive_time():
    ended = []
    audio = AudioForPid(playing_pid=70)
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
                "entertainment_idle_threshold_seconds": 3,
                "min_session_seconds": 1,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=ended.append,
        audio_detector=audio,
    )
    video = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 70,
    }

    for _ in range(4):
        tracker.tick(0, video)

    assert ended == []
    assert tracker.current_session.passive_seconds == 4
    assert tracker._persistent_idle == 4

    audio.playing_pid = None
    for _ in range(4):
        tracker.tick(0, video)

    assert len(ended) == 1
    session = ended[0]
    assert session.passive_seconds == 4
    assert session.idle_seconds == 0
    _assert_attention_conserved(session)
