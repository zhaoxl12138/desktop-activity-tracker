from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from daylens.session_tracker import ActivitySession, SessionTracker


class MappingClassifier:
    _MAPPING = {
        "Code.exe": ("coding", "Coding", "interactive_required"),
        "Notes.exe": ("reading", "Reading", "interactive_required"),
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


class WorkVoiceForPid(AudioForPid):
    def __init__(self, voice_pid):
        super().__init__(playing_pid=None)
        self.voice_pid = voice_pid
        self.voice_checks = []

    def is_voice_active(self, pid, exe_path=""):
        self.voice_checks.append((pid, exe_path))
        return pid == self.voice_pid


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


def test_idle_work_voice_counts_as_engaged_without_keyboard_or_mouse():
    audio = WorkVoiceForPid(10)
    tracker = _tracker(idle_threshold=1, audio_detector=audio)
    window = {
        "process_name": "Code.exe",
        "window_title": "Voice coding",
        "exe_path": r"C:\\Apps\\Code.exe",
        "pid": 10,
    }

    tracker.tick(0, window)
    tracker.tick(0, window)
    snapshot = tracker.tick(0, window)
    session = tracker.current_session

    assert session.engaged_seconds == 3
    assert session.passive_seconds == 0
    assert session.idle_seconds == 0
    assert session.effective_seconds == 3
    assert snapshot["attention_state"] == "engaged"
    assert snapshot["is_effective"] is True
    assert audio.voice_checks[-1] == (10, r"C:\\Apps\\Code.exe")
    _assert_attention_conserved(session)


def test_background_audio_does_not_keep_idle_work_effective():
    tracker = _tracker(
        idle_threshold=1,
        audio_detector=WorkVoiceForPid(999),
    )
    window = {
        "process_name": "Code.exe",
        "window_title": "Paused voice coding",
        "exe_path": r"C:\\Apps\\Code.exe",
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


def test_idle_back_correction_spans_current_and_pending_ledgers():
    tracker = _tracker(idle_threshold=3, passive_threshold=99)
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 71,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 72,
    }
    tracker.tick(0, coding)
    tracker.tick(0, coding)
    tracker.tick(0, social)
    tracker.tick(0, social)

    session = tracker.current_session
    pending = tracker._pending_switch
    assert session.duration_seconds == 2
    assert session.engaged_seconds == 0
    assert session.passive_seconds == 0
    assert session.idle_seconds == 2
    _assert_attention_conserved(session)
    assert pending["engaged_during_grace"] == 0
    assert pending["passive_during_grace"] == 0
    assert pending["idle_during_grace"] == 2
    assert sum(
        pending[key]
        for key in (
            "engaged_during_grace",
            "passive_during_grace",
            "idle_during_grace",
        )
    ) == 2


def test_idle_back_correction_preserves_each_sessions_audio_evidence():
    tracker = _tracker(
        idle_threshold=3,
        passive_threshold=99,
        audio_detector=AudioForPid(playing_pid=81),
    )
    video = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 81,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 82,
    }

    tracker.tick(0, video)
    tracker.tick(0, video)
    tracker.tick(0, social)
    tracker.tick(0, social)

    session = tracker.current_session
    pending = tracker._pending_switch
    assert session.category_key == "video"
    assert session.engaged_seconds == 0
    assert session.passive_seconds == 2
    assert session.idle_seconds == 0
    _assert_attention_conserved(session)
    assert pending["engaged_during_grace"] == 0
    assert pending["passive_during_grace"] == 0
    assert pending["idle_during_grace"] == 2


def test_immediate_video_reset_starts_a_bounded_new_idle_epoch():
    persisted = {}

    def persist(session):
        persisted[session.session_id] = (
            session.engaged_seconds,
            session.passive_seconds,
            session.idle_seconds,
        )
        return True

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 3,
                "entertainment_idle_threshold_seconds": 99,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=persist,
        audio_detector=AudioForPid(playing_pid=90),
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 89,
    }
    video = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 90,
    }
    tracker.tick(0, coding)
    tracker.tick(0, coding)
    old_session = tracker.current_session

    ledger_sizes = []
    for _ in range(4):
        tracker.tick(0, video)
        ledger_sizes.append(len(tracker._provisional_attention))

    assert persisted[old_session.session_id] == (2, 0, 0)
    assert old_session.engaged_seconds == 2
    assert old_session.passive_seconds == 0
    assert old_session.idle_seconds == 0
    assert max(ledger_sizes) <= tracker.idle_threshold
    assert tracker.current_session.engaged_seconds == 0
    assert tracker.current_session.passive_seconds == 4
    assert tracker.current_session.idle_seconds == 0
    _assert_attention_conserved(tracker.current_session)


def test_pending_started_after_idle_correction_does_not_reclassify_active_time():
    tracker = _tracker(idle_threshold=1, passive_threshold=99)
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 77,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 78,
    }
    tracker.mark_user_active()
    tracker.tick(0, coding)
    tracker.tick(0, coding)
    tracker.tick(0, coding)
    assert tracker._idle_corrected is True
    assert tracker.current_session.engaged_seconds == 1

    tracker.tick(0, social)

    assert tracker.current_session.engaged_seconds == 1
    assert tracker.current_session.idle_seconds == 2
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
    assert sum(
        tracker._pending_switch[key]
        for key in (
            "engaged_during_grace",
            "passive_during_grace",
            "idle_during_grace",
        )
    ) == 1
    assert failed_snapshot["process_name"] == "VLC.exe"
    assert failed_snapshot["category_key"] == "video"
    assert len(callback_sessions) == 1

    tracker.tick(0, video)

    assert tracker.current_session is not original_session
    assert tracker.current_session.process_name == "VLC.exe"
    assert tracker.current_session.duration_seconds == 2
    _assert_attention_conserved(tracker.current_session)
    assert tracker._pending_switch is None
    assert len(callback_sessions) == 2


def test_immediate_entertainment_switch_exception_accounts_failed_tick_once():
    persist_attempts = 0

    def persist(_session):
        nonlocal persist_attempts
        persist_attempts += 1
        if persist_attempts == 1:
            raise OSError("database busy")
        return True

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 60,
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
        "pid": 48,
    }
    video = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 49,
    }
    tracker.tick(0, coding)

    with pytest.raises(OSError, match="database busy"):
        tracker.tick(0, video)

    assert tracker._pending_switch is not None
    assert sum(
        tracker._pending_switch[key]
        for key in (
            "engaged_during_grace",
            "passive_during_grace",
            "idle_during_grace",
        )
    ) == 1

    tracker.tick(0, video)

    assert persist_attempts == 2
    assert tracker._pending_switch is None
    assert tracker.current_session.process_name == "VLC.exe"
    assert tracker.current_session.duration_seconds == 2
    _assert_attention_conserved(tracker.current_session)


@pytest.mark.parametrize("boundary", ["app_change", "title_change", "cross_day"])
def test_session_boundary_exception_accounts_failed_tick_once(boundary):
    attempts = 0

    def persist(_session):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("database busy")
        return True

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 60,
                "entertainment_idle_threshold_seconds": 300,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=persist,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 52,
    }
    if boundary == "title_change":
        initial = {
            "process_name": "VLC.exe",
            "window_title": "Episode 1",
            "exe_path": "",
            "pid": 53,
        }
        target = {**initial, "window_title": "Episode 2"}
    elif boundary == "app_change":
        initial = coding
        target = {
            "process_name": "Notes.exe",
            "window_title": "notes.md",
            "exe_path": "",
            "pid": 54,
        }
    else:
        initial = coding
        target = coding

    tracker.tick(0, initial)
    old_session = tracker.current_session
    if boundary == "cross_day":
        old_session.date = "1999-01-01"

    with pytest.raises(OSError, match="database busy"):
        tracker.tick(0, target)

    assert tracker.current_session is old_session
    assert old_session.duration_seconds == 2
    _assert_attention_conserved(old_session)

    tracker.tick(0, target)

    assert attempts == 2
    assert old_session.duration_seconds == 2
    _assert_attention_conserved(old_session)
    assert tracker.current_session is not old_session
    assert tracker.current_session.duration_seconds == 1
    _assert_attention_conserved(tracker.current_session)


@pytest.mark.parametrize("boundary", ["app_change", "title_change", "classifier"])
def test_ordinary_boundary_inherits_physical_idle_without_gifting_engaged(boundary):
    classifier = (
        ConfigurableVersionClassifier("rules-old")
        if boundary == "classifier"
        else MappingClassifier()
    )
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
                "entertainment_idle_threshold_seconds": 99,
            }
        },
        classifier=classifier,
        on_session_end=lambda _session: True,
    )
    if boundary == "title_change":
        initial = {
            "process_name": "VLC.exe",
            "window_title": "Episode 1",
            "exe_path": "",
            "pid": 55,
        }
        target = {**initial, "window_title": "Episode 2"}
    else:
        initial = {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 56,
        }
        target = (
            {
                "process_name": "Notes.exe",
                "window_title": "notes.md",
                "exe_path": "",
                "pid": 57,
            }
            if boundary == "app_change"
            else initial
        )

    tracker.tick(0, initial)
    tracker.tick(0, initial)
    assert tracker._persistent_idle == 2
    if boundary == "classifier":
        assert tracker.replace_classifier(
            ConfigurableVersionClassifier("rules-new")
        ) is True

    snapshot = tracker.tick(0, target)
    session = tracker.current_session

    assert tracker._persistent_idle == 3
    assert session.engaged_seconds == 0
    assert session.passive_seconds == 0
    assert session.idle_seconds == 1
    assert snapshot["attention_state"] == "idle"
    assert snapshot["is_effective"] is False
    _assert_attention_conserved(session)


@pytest.mark.parametrize("boundary", ["app_change", "title_change", "classifier"])
def test_provisional_idle_window_is_rewritten_across_ordinary_boundary(boundary):
    persisted = {}

    def persist(session):
        persisted[session.session_id] = (
            session.engaged_seconds,
            session.passive_seconds,
            session.idle_seconds,
            session.duration_seconds,
            session.classification_version,
        )
        return True

    classifier = (
        ConfigurableVersionClassifier("rules-old")
        if boundary == "classifier"
        else MappingClassifier()
    )
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 3,
                "entertainment_idle_threshold_seconds": 99,
            }
        },
        classifier=classifier,
        on_session_end=persist,
        on_session_rewrite=persist,
    )
    if boundary == "title_change":
        initial = {
            "process_name": "VLC.exe",
            "window_title": "Episode 1",
            "exe_path": "",
            "pid": 83,
        }
        target = {**initial, "window_title": "Episode 2"}
    else:
        initial = {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 84,
        }
        target = (
            {
                "process_name": "Notes.exe",
                "window_title": "notes.md",
                "exe_path": "",
                "pid": 85,
            }
            if boundary == "app_change"
            else initial
        )

    tracker.tick(0, initial)
    tracker.tick(0, initial)
    old_session = tracker.current_session
    if boundary == "classifier":
        assert tracker.replace_classifier(
            ConfigurableVersionClassifier("rules-new")
        ) is True
    tracker.tick(0, target)
    tracker.tick(0, target)

    assert persisted[old_session.session_id][:4] == (0, 0, 2, 2)
    assert tracker.current_session.engaged_seconds == 0
    assert tracker.current_session.passive_seconds == 0
    assert tracker.current_session.idle_seconds == 2
    _assert_attention_conserved(tracker.current_session)


@pytest.mark.parametrize("failure_mode", ["return_false", "exception"])
def test_failed_provisional_boundary_rewrite_retries_without_double_counting(
    failure_mode,
):
    outcomes = iter([True, failure_mode, True])
    persisted = {}
    attempts = []

    def persist(session):
        outcome = next(outcomes)
        attempts.append((session.session_id, outcome))
        if outcome == "exception":
            raise OSError("database busy")
        if outcome is True:
            persisted[session.session_id] = (
                session.engaged_seconds,
                session.passive_seconds,
                session.idle_seconds,
                session.duration_seconds,
            )
        return False if outcome == "return_false" else outcome

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 3,
                "entertainment_idle_threshold_seconds": 99,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=persist,
        on_session_rewrite=persist,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 88,
    }
    notes = {
        "process_name": "Notes.exe",
        "window_title": "notes.md",
        "exe_path": "",
        "pid": 89,
    }
    tracker.tick(0, coding)
    tracker.tick(0, coding)
    old_session = tracker.current_session
    tracker.tick(0, notes)

    if failure_mode == "exception":
        with pytest.raises(OSError, match="database busy"):
            tracker.tick(0, notes)
    else:
        tracker.tick(0, notes)
    tracker.tick(0, notes)

    assert len(attempts) == 3
    assert persisted[old_session.session_id] == (0, 0, 2, 2)
    assert tracker.current_session.engaged_seconds == 0
    assert tracker.current_session.passive_seconds == 0
    assert tracker.current_session.idle_seconds == 3
    _assert_attention_conserved(tracker.current_session)


def test_permanent_rewrite_failure_is_bounded_and_backpressures_sampling():
    rewrite_attempts = []

    def rewrite(session):
        rewrite_attempts.append(session.session_id)
        return False

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
                "entertainment_idle_threshold_seconds": 99,
                "attention_rewrite_queue_size": 2,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=lambda _session: True,
        on_session_rewrite=rewrite,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 91,
    }
    notes = {
        "process_name": "Notes.exe",
        "window_title": "notes.md",
        "exe_path": "",
        "pid": 92,
    }

    tracker.tick(0, coding)
    tracker.tick(0, notes)
    tracker.mark_user_active()
    tracker.tick(0, notes)
    tracker.tick(0, coding)
    tracker.tick(0, notes)

    pending = tracker.pending_rewrite_sessions()
    assert len(pending) == 2
    assert len({session.session_id for session in pending}) == 2
    before = (
        tracker.current_session.session_id,
        tracker.current_session.duration_seconds,
        tracker.current_session.engaged_seconds,
        tracker.current_session.passive_seconds,
        tracker.current_session.idle_seconds,
    )
    tracker.mark_user_active()

    with pytest.raises(RuntimeError, match="rewrite capacity"):
        tracker.tick(0, notes)

    assert len(tracker.pending_rewrite_sessions()) == 2
    assert len(tracker._provisional_attention) <= tracker.idle_threshold
    assert (
        tracker.current_session.session_id,
        tracker.current_session.duration_seconds,
        tracker.current_session.engaged_seconds,
        tracker.current_session.passive_seconds,
        tracker.current_session.idle_seconds,
    ) == before
    assert rewrite_attempts


def test_provisional_boundaries_stop_before_exceeding_rewrite_capacity():
    ended = []
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 10,
                "entertainment_idle_threshold_seconds": 99,
                "attention_rewrite_queue_size": 2,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=lambda session: ended.append(session.session_id) or True,
        on_session_rewrite=lambda _session: False,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 93,
    }
    notes = {
        "process_name": "Notes.exe",
        "window_title": "notes.md",
        "exe_path": "",
        "pid": 94,
    }

    tracker.tick(0, coding)
    tracker.tick(0, notes)
    tracker.tick(0, coding)
    blocked_session = tracker.current_session

    with pytest.raises(RuntimeError, match="rewrite capacity"):
        tracker.tick(0, notes)

    assert len(ended) == 2
    assert tracker.current_session is blocked_session
    assert tracker.current_session.process_name == "Code.exe"
    assert len(
        {
            entry["owner"].session_id
            for entry in tracker._provisional_attention
            if entry["persisted"]
        }
    ) == 2


def test_runtime_shrink_waits_for_reserved_provisional_owners_to_drain():
    rewritten = []

    def rewrite(session):
        rewritten.append(session.session_id)
        return True

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 10,
                "entertainment_idle_threshold_seconds": 99,
                "attention_rewrite_queue_size": 3,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=lambda _session: True,
        on_session_rewrite=rewrite,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 95,
    }
    notes = {
        "process_name": "Notes.exe",
        "window_title": "notes.md",
        "exe_path": "",
        "pid": 96,
    }

    tracker.tick(0, coding)
    tracker.tick(0, notes)
    tracker.tick(0, coding)
    tracker.tick(0, notes)
    reserved_ids = tracker._rewrite_owner_ids(tracker._provisional_attention)
    assert len(reserved_ids) == 3
    assert tracker.pending_rewrite_sessions() == ()

    tracker.set_rewrite_capacity(1)

    assert tracker.rewrite_capacity_requested == 1
    assert tracker.rewrite_capacity_effective == 3
    for _ in range(7):
        tracker.tick(0, notes)

    assert set(rewritten) == reserved_ids
    assert tracker.pending_rewrite_sessions() == ()
    assert tracker.rewrite_capacity_effective == 1
    before_duration = tracker.current_session.duration_seconds

    tracker.tick(0, notes)

    assert tracker.current_session.duration_seconds == before_duration + 1


def test_pending_rewrite_snapshot_cannot_mutate_tracker_owned_session():
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
                "entertainment_idle_threshold_seconds": 99,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=lambda _session: True,
        on_session_rewrite=lambda _session: False,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 97,
    }
    notes = {
        "process_name": "Notes.exe",
        "window_title": "notes.md",
        "exe_path": "",
        "pid": 98,
    }
    tracker.tick(0, coding)
    tracker.tick(0, notes)

    snapshot = tracker.pending_rewrite_sessions()
    assert len(snapshot) == 1
    session_id = snapshot[0].session_id
    snapshot[0].window_title = "mutated outside tracker"
    snapshot[0].duration_seconds = 999
    snapshot[0].engaged_seconds = 999
    snapshot[0].passive_seconds = 999
    snapshot[0].effective_seconds = 1998
    snapshot[0].idle_seconds = 999

    internal_snapshot = tracker.pending_rewrite_sessions()
    assert internal_snapshot[0].window_title == "main.py"
    assert internal_snapshot[0].duration_seconds == 1
    assert internal_snapshot[0].engaged_seconds == 0
    assert internal_snapshot[0].passive_seconds == 0
    assert internal_snapshot[0].effective_seconds == 0
    assert internal_snapshot[0].idle_seconds == 1

    tracker.acknowledge_pending_rewrites([session_id])

    assert tracker.pending_rewrite_sessions() == ()


def test_video_title_change_after_sixty_idle_seconds_starts_idle():
    ended = []
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 60,
                "entertainment_idle_threshold_seconds": 999,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=lambda session: ended.append(session) or True,
    )
    first_episode = {
        "process_name": "VLC.exe",
        "window_title": "Episode 1",
        "exe_path": "",
        "pid": 58,
    }
    second_episode = {**first_episode, "window_title": "Episode 2"}
    for _ in range(61):
        tracker.tick(0, first_episode)

    snapshot = tracker.tick(0, second_episode)

    assert ended[0].engaged_seconds == 0
    assert ended[0].idle_seconds == 61
    assert tracker._persistent_idle == 62
    assert tracker.current_session.engaged_seconds == 0
    assert tracker.current_session.idle_seconds == 1
    assert snapshot["attention_state"] == "idle"
    _assert_attention_conserved(ended[0])
    _assert_attention_conserved(tracker.current_session)


def test_legacy_video_title_change_keeps_historical_idle_accounting():
    """The new pause-aware policy is opt-in; legacy fixtures stay unchanged."""
    ended = []
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 60,
                "entertainment_idle_threshold_seconds": 999,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=lambda session: ended.append(session) or True,
    )
    first_episode = {
        "process_name": "VLC.exe",
        "window_title": "Episode 1",
        "exe_path": "",
        "pid": 58,
    }
    second_episode = {**first_episode, "window_title": "Episode 2"}
    for _ in range(61):
        tracker.tick(0, first_episode)
    tracker.tick(0, second_episode)
    assert ended[0].idle_seconds == 61


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


def test_pending_silent_video_streak_is_inherited_and_trimmed_after_retries():
    outcomes = iter([False, "raise", False, False, True, True])
    attempts = []

    def persist(session):
        attempts.append(
            (
                session.session_id,
                session.process_name,
                session.duration_seconds,
                session.engaged_seconds,
                session.passive_seconds,
                session.idle_seconds,
                session.switch_reason,
            )
        )
        outcome = next(outcomes)
        if outcome == "raise":
            raise OSError("database busy")
        return outcome

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
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 75,
    }
    video = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 76,
    }
    tracker.tick(0, coding)

    tracker.tick(0, video)
    with pytest.raises(OSError, match="database busy"):
        tracker.tick(0, video)
    tracker.tick(0, video)
    tracker.tick(0, video)

    pending = tracker._pending_switch
    assert pending["video_silent_idle"] == 4
    assert pending["engaged_during_grace"] == 0
    assert pending["passive_during_grace"] == 0
    assert pending["idle_during_grace"] == 4

    tracker.tick(0, video)

    assert tracker.current_session is None
    assert tracker._pending_switch is None
    assert tracker._awaiting_activity is True
    assert len(attempts) == 6
    video_attempt = attempts[-1]
    assert video_attempt[1] == "VLC.exe"
    assert video_attempt[2:6] == (0, 0, 0, 0)
    assert video_attempt[6] == "entertainment_idle"


def test_non_video_grace_interrupts_silent_video_streak_when_cancelled():
    ended = []
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
                "entertainment_idle_threshold_seconds": 2,
                "cross_group_grace_seconds": 30,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=lambda session: ended.append(session) or True,
    )
    video = {
        "process_name": "VLC.exe",
        "window_title": "Movie",
        "exe_path": "",
        "pid": 86,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 87,
    }

    tracker.tick(0, video)
    tracker.tick(0, video)
    assert tracker._video_silent_idle == 2
    tracker.tick(0, social)
    assert tracker._pending_switch["video_silent_idle"] == 0

    tracker.tick(0, video)

    assert ended == []
    assert tracker.current_session is not None
    assert tracker.current_session.category_key == "video"
    assert tracker._pending_switch is None
    assert tracker._video_silent_idle == 1
    _assert_attention_conserved(tracker.current_session)


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


@pytest.mark.parametrize("failure_mode", ["return_false", "exception"])
def test_system_gap_failure_rolls_back_pending_fold_and_retries_once(failure_mode):
    attempts = []
    successful_ids = []

    def persist(session):
        attempts.append(
            (
                session.duration_seconds,
                session.engaged_seconds,
                session.passive_seconds,
                session.idle_seconds,
                session.switch_reason,
            )
        )
        if len(attempts) == 1:
            if failure_mode == "exception":
                raise OSError("database busy")
            return False
        successful_ids.append(session.session_id)
        return True

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
                "entertainment_idle_threshold_seconds": 99,
            }
        },
        classifier=MappingClassifier(),
        on_session_end=persist,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 73,
    }
    social = {
        "process_name": "Chat.exe",
        "window_title": "Friends",
        "exe_path": "",
        "pid": 74,
    }
    tracker.tick(0, coding)
    tracker.tick(0, social)
    session = tracker.current_session
    pending = tracker._pending_switch
    original_session_state = (
        session.end_time,
        session.switch_reason,
        session.duration_seconds,
        session.engaged_seconds,
        session.passive_seconds,
        session.effective_seconds,
        session.idle_seconds,
    )
    original_idle_state = (
        tracker._persistent_idle,
        tracker._idle_corrected,
        tracker._video_silent_idle,
        tracker._awaiting_activity,
    )
    tracker._last_tick_wall_time -= timedelta(seconds=600)
    retry_wall_time = tracker._last_tick_wall_time

    if failure_mode == "exception":
        with pytest.raises(OSError, match="database busy"):
            tracker.tick(0, social)
    else:
        tracker.tick(0, social)

    assert tracker.current_session is session
    assert tracker._pending_switch is pending
    assert (
        session.end_time,
        session.switch_reason,
        session.duration_seconds,
        session.engaged_seconds,
        session.passive_seconds,
        session.effective_seconds,
        session.idle_seconds,
    ) == original_session_state
    assert (
        tracker._persistent_idle,
        tracker._idle_corrected,
        tracker._video_silent_idle,
        tracker._awaiting_activity,
    ) == original_idle_state
    assert tracker._last_tick_wall_time == retry_wall_time

    tracker.tick(0, social)

    assert tracker.current_session is None
    assert tracker._pending_switch is None
    assert attempts[0] == attempts[1]
    assert attempts[1][-1] == "system_gap"
    assert successful_ids == [session.session_id]
    assert session.duration_seconds == 2
    _assert_attention_conserved(session)


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


@pytest.mark.parametrize("failure_mode", ["exception", "return_false"])
def test_video_auto_close_failure_rolls_back_before_retry(failure_mode):
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
        if len(attempts) == 1:
            if failure_mode == "exception":
                raise OSError("database busy")
            return False
        return True

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
        on_session_end=persist,
    )
    session = tracker._current = ActivitySession(
        session_id="video-retry",
        start_time=datetime.now(),
        end_time=datetime.now(),
        date=datetime.now().strftime("%Y-%m-%d"),
        process_name="VLC.exe",
        exe_path="",
        window_title="Movie",
        normalized_title="Movie",
        category_key="video",
        category_name="Video",
        active_rule="passive_allowed",
        duration_seconds=10,
        effective_seconds=10,
        engaged_seconds=10,
        initial_title="Movie",
    )

    for _ in range(3):
        tracker._tick_current(10, datetime.now())

    if failure_mode == "exception":
        with pytest.raises(OSError, match="database busy"):
            tracker._tick_current(10, datetime.now())
    else:
        tracker._tick_current(10, datetime.now())

    assert tracker.current_session is session
    assert session.switch_reason == ""
    assert session.duration_seconds == 14
    assert session.engaged_seconds == 10
    assert session.passive_seconds == 0
    assert session.idle_seconds == 4
    assert tracker._video_silent_idle == 4
    assert tracker._awaiting_activity is False
    _assert_attention_conserved(session)

    tracker._tick_current(10, datetime.now())

    assert tracker.current_session is None
    assert attempts[0] == attempts[1] == (10, 10, 0, 0)
    assert tracker._awaiting_activity is True
