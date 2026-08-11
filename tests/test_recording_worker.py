from __future__ import annotations

import threading
from datetime import datetime

import pytest

from daylens.gui import worker as worker_module
from daylens.session_tracker import ActivitySession, SessionTracker


class TrackerStub:
    def __init__(self):
        self.idle_threshold = 60
        self.entertainment_idle_threshold = 300
        self.min_session = 2
        self.sample_interval = 1
        self.flush_interval = 5
        self.cross_group_grace = 30
        self._max_pending_attention_rewrites = 100
        self.classifier = object()
        self.replacement_calls = []
        self.replace_result = True
        self.active_marks = 0

    def mark_user_active(self):
        self.active_marks += 1

    def replace_classifier(self, replacement_classifier):
        self.replacement_calls.append(replacement_classifier)
        if not self.replace_result:
            return False
        self.classifier = replacement_classifier
        return True


class StaticClassifier:
    def classify(self, _process_name, _window_title):
        return {
            "category_key": "coding",
            "category_name": "Coding",
            "active_rule": "interactive_required",
        }


class VersionedStaticClassifier:
    def __init__(self, classification_version):
        self.classification_version = classification_version

    def classify(self, process_name, _window_title):
        mapping = {
            "Code.exe": ("coding", "Coding", "interactive_required"),
            "Chat.exe": ("social", "Social", "passive_allowed"),
        }
        category_key, category_name, active_rule = mapping[process_name]
        return {
            "category_key": category_key,
            "category_name": category_name,
            "active_rule": active_rule,
        }


class FakeListener:
    instances = []

    def __init__(self, on_press):
        self.on_press = on_press
        self.started = False
        self.stopped = False
        self.__class__.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeStore:
    def __init__(self, failures=None):
        self.failures = list(failures or [])
        self.attempts = []
        self.closed = False

    def persist_session(self, session):
        self.attempts.append(session)
        if self.failures:
            error = self.failures.pop(0)
            if error is not None:
                raise error
        session._db_row_id = session._db_row_id if session._db_row_id > 0 else 1
        return session._db_row_id

    def close(self):
        self.closed = True


class PerSessionStore:
    def __init__(self):
        self.queueing = True
        self.remaining_failures = {}
        self.attempt_ids = []

    def persist_session(self, session):
        self.attempt_ids.append(session.session_id)
        if self.queueing:
            raise OSError("offline")
        failures = self.remaining_failures.get(session.session_id, 0)
        if failures:
            self.remaining_failures[session.session_id] = failures - 1
            raise OSError(f"{session.session_id} still offline")
        session._db_row_id = session._db_row_id if session._db_row_id > 0 else 1
        return session._db_row_id

    def close(self):
        pass


def _session(session_id):
    now = datetime.now()
    return ActivitySession(
        session_id=session_id,
        start_time=now,
        end_time=now,
        date=now.strftime("%Y-%m-%d"),
        process_name="Code.exe",
        exe_path="",
        window_title="main.py",
        normalized_title="main.py",
        category_key="coding",
        category_name="Coding",
        active_rule="interactive_required",
        duration_seconds=1,
        effective_seconds=1,
    )


def _patch_run_dependencies(monkeypatch, store):
    FakeListener.instances.clear()
    monkeypatch.setattr(
        worker_module.classifier,
        "Classifier",
        lambda *_args: StaticClassifier(),
    )
    monkeypatch.setattr(
        worker_module,
        "SessionRuntimeStore",
        lambda _db_path: store,
    )
    monkeypatch.setattr(worker_module.keyboard, "Listener", FakeListener)
    monkeypatch.setattr(worker_module, "AudioDetector", None)
    monkeypatch.setattr(worker_module.activity_detector, "get_idle_seconds", lambda: 0)
    monkeypatch.setattr(
        worker_module.window_detector,
        "get_foreground_window_info",
        lambda: {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 100,
        },
    )
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr(
        "daylens.session_tracker._get_keyboard_snapshot",
        lambda: bytes(256),
    )


class ManualClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class CadenceSpy:
    def __init__(self):
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1

    def next_sleep_ms(self, _interval_seconds):
        return 0


def test_worker_sleeps_only_for_remaining_sampling_interval(monkeypatch):
    clock = ManualClock()
    store = FakeStore()
    _patch_run_dependencies(monkeypatch, store)
    monkeypatch.setattr(
        worker_module.window_detector,
        "get_foreground_window_info",
        lambda: clock.advance(0.06)
        or {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 100,
        },
    )
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"sample_interval_seconds": 1}},
        monotonic_clock=clock.monotonic,
    )
    sleeps = []

    def capture_sleep(milliseconds):
        sleeps.append(milliseconds)
        worker.stop()

    worker._sleep_check = capture_sleep

    worker.run()

    assert sleeps == [940]


def test_worker_rebases_after_full_missed_interval_without_catch_up_loop(
    monkeypatch,
):
    clock = ManualClock()
    store = FakeStore()
    _patch_run_dependencies(monkeypatch, store)
    processing_times = iter([2.1, 0.06])

    def foreground_window():
        clock.advance(next(processing_times))
        return {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 100,
        }

    monkeypatch.setattr(
        worker_module.window_detector,
        "get_foreground_window_info",
        foreground_window,
    )
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"sample_interval_seconds": 1}},
        monotonic_clock=clock.monotonic,
    )
    sleeps = []

    def capture_sleep(milliseconds):
        sleeps.append(milliseconds)
        if len(sleeps) == 2:
            worker.stop()

    worker._sleep_check = capture_sleep

    worker.run()

    assert sleeps == [0, 940]


def test_paused_worker_resets_sampling_cadence(monkeypatch):
    store = FakeStore()
    _patch_run_dependencies(monkeypatch, store)
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    cadence = CadenceSpy()
    worker._sampling_cadence = cadence
    worker.pause()
    worker._sleep_check = lambda _milliseconds: worker.stop()

    worker.run()

    assert cadence.reset_calls == 2


def test_resume_starts_a_fresh_cadence_without_immediate_catch_up(monkeypatch):
    clock = ManualClock()
    store = FakeStore()
    _patch_run_dependencies(monkeypatch, store)
    monkeypatch.setattr(
        worker_module.window_detector,
        "get_foreground_window_info",
        lambda: clock.advance(0.06)
        or {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 100,
        },
    )
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"sample_interval_seconds": 1}},
        monotonic_clock=clock.monotonic,
    )
    sleeps = []
    worker.pause()

    def capture_sleep(milliseconds):
        sleeps.append(milliseconds)
        if len(sleeps) == 1:
            clock.advance(1.0)
            worker.resume()
        else:
            worker.stop()

    worker._sleep_check = capture_sleep

    worker.run()

    assert sleeps == [1000, 940]


def test_worker_control_state_uses_threading_events():
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    event_type = type(threading.Event())

    assert isinstance(worker._running, event_type)
    assert isinstance(worker._paused, event_type)
    assert isinstance(worker._pause_requested, event_type)


def test_settings_update_is_applied_only_when_worker_consumes_command(monkeypatch):
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    tracker = TrackerStub()
    cadence = CadenceSpy()
    worker._tracker = tracker
    worker._sampling_cadence = cadence
    replacement_classifier = object()
    monkeypatch.setattr(
        worker_module.classifier,
        "Classifier",
        lambda *_args: replacement_classifier,
    )
    updated = {
        "tracker": {
            "sample_interval_seconds": 3,
            "flush_interval_seconds": 7,
            "idle_threshold_seconds": 90,
            "entertainment_idle_threshold_seconds": 600,
            "min_session_seconds": 4,
            "cross_group_grace_seconds": 45,
            "persistence_retry_queue_size": 12,
        }
    }

    worker.update_settings(updated)

    assert tracker.sample_interval == 1
    assert worker.sample_interval == 1

    worker._consume_commands()

    assert tracker.sample_interval == 3
    assert tracker.flush_interval == 7
    assert tracker.idle_threshold == 90
    assert tracker.entertainment_idle_threshold == 600
    assert tracker.min_session == 4
    assert tracker.cross_group_grace == 45
    assert tracker._max_pending_attention_rewrites == 12
    assert tracker.classifier is replacement_classifier
    assert tracker.replacement_calls == [replacement_classifier]
    assert worker.sample_interval == 3
    assert cadence.reset_calls == 1


def test_classifier_reload_is_applied_only_at_worker_boundary(monkeypatch):
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    tracker = TrackerStub()
    original_classifier = tracker.classifier
    replacement_classifier = object()
    construction_threads = []
    worker._tracker = tracker

    def create_classifier(*_args):
        construction_threads.append(threading.get_ident())
        return replacement_classifier

    monkeypatch.setattr(worker_module.classifier, "Classifier", create_classifier)

    worker.reload_classifier()
    assert tracker.classifier is original_classifier

    worker._consume_commands()

    assert tracker.classifier is replacement_classifier
    assert tracker.replacement_calls == [replacement_classifier]
    assert construction_threads == [threading.get_ident()]


def test_classifier_reload_failure_keeps_old_classifier_and_reports_error(monkeypatch):
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    tracker = TrackerStub()
    tracker.replace_result = False
    original_classifier = tracker.classifier
    replacement_classifier = object()
    errors = []
    worker._tracker = tracker
    worker.error_occurred.connect(errors.append)
    monkeypatch.setattr(
        worker_module.classifier,
        "Classifier",
        lambda *_args: replacement_classifier,
    )

    worker.reload_classifier()
    worker._consume_commands()

    assert tracker.replacement_calls == [replacement_classifier]
    assert tracker.classifier is original_classifier
    assert worker.health.status == "degraded"
    assert errors == ["classifier replacement could not finish current session"]


def test_settings_reload_failure_keeps_previous_settings_and_classifier(monkeypatch):
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    tracker = TrackerStub()
    tracker.replace_result = False
    cadence = CadenceSpy()
    old_config = dict(worker.config)
    original_classifier = tracker.classifier
    replacement_classifier = object()
    errors = []
    worker._tracker = tracker
    worker._sampling_cadence = cadence
    worker.error_occurred.connect(errors.append)
    monkeypatch.setattr(
        worker_module.classifier,
        "Classifier",
        lambda *_args: replacement_classifier,
    )

    worker.update_settings({"tracker": {"sample_interval_seconds": 9}})
    worker._consume_commands()

    assert tracker.replacement_calls == [replacement_classifier]
    assert tracker.classifier is original_classifier
    assert worker.config == old_config
    assert worker.sample_interval == 1
    assert tracker.sample_interval == 1
    assert cadence.reset_calls == 0
    assert worker.health.status == "degraded"
    assert errors == ["classifier replacement could not finish current session"]


def test_classifier_reload_splits_active_session_at_rule_version_boundary(
    monkeypatch,
):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr(
        "daylens.session_tracker._get_keyboard_snapshot",
        lambda: bytes(256),
    )
    ended = []
    original_classifier = VersionedStaticClassifier("rules-old")
    replacement_classifier = VersionedStaticClassifier("rules-new")
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=original_classifier,
        on_session_end=lambda session: ended.append(session) or True,
    )
    window = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 200,
    }
    tracker.tick(0, window)
    old_session = tracker.current_session
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    worker._tracker = tracker
    monkeypatch.setattr(
        worker_module.classifier,
        "Classifier",
        lambda *_args: replacement_classifier,
    )

    worker.reload_classifier()
    worker._consume_commands()

    assert ended == [old_session]
    assert old_session.classification_version == "rules-old"
    assert tracker.current_session is None
    assert tracker.classifier is replacement_classifier
    assert tracker.classification_version == "rules-new"

    tracker.tick(0, window)
    assert tracker.current_session.classification_version == "rules-new"


def test_settings_reload_clears_pending_state_at_rule_version_boundary(
    monkeypatch,
):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr(
        "daylens.session_tracker._get_keyboard_snapshot",
        lambda: bytes(256),
    )
    ended = []
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=VersionedStaticClassifier("rules-old"),
        on_session_end=lambda session: ended.append(session) or True,
    )
    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 201,
        },
    )
    tracker.tick(
        0,
        {
            "process_name": "Chat.exe",
            "window_title": "Friends",
            "exe_path": "",
            "pid": 202,
        },
    )
    pending_seconds = (
        tracker._pending_switch["engaged_during_grace"]
        + tracker._pending_switch["passive_during_grace"]
        + tracker._pending_switch["idle_during_grace"]
    )
    old_duration = tracker.current_session.duration_seconds
    replacement_classifier = VersionedStaticClassifier("rules-new")
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    worker._tracker = tracker
    monkeypatch.setattr(
        worker_module.classifier,
        "Classifier",
        lambda *_args: replacement_classifier,
    )

    worker.update_settings({"tracker": {"sample_interval_seconds": 3}})
    worker._consume_commands()

    assert len(ended) == 1
    assert ended[0].duration_seconds == old_duration + pending_seconds
    assert ended[0].classification_version == "rules-old"
    assert tracker.current_session is None
    assert tracker._pending_switch is None
    assert tracker.classifier is replacement_classifier
    assert tracker.classification_version == "rules-new"
    assert tracker.sample_interval == 3


def test_keyboard_callback_only_sets_event_until_worker_boundary():
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    tracker = TrackerStub()
    worker._tracker = tracker

    worker._on_key_press(None)

    assert tracker.active_marks == 0
    assert worker._keyboard_activity.is_set()

    worker._consume_keyboard_activity()

    assert tracker.active_marks == 1
    assert not worker._keyboard_activity.is_set()


def test_run_retries_failed_final_session_and_cleans_up(monkeypatch):
    store = FakeStore([OSError("database busy"), None])
    _patch_run_dependencies(monkeypatch, store)
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"persistence_shutdown_retry_attempts": 3}},
    )
    health_updates = []
    errors = []
    worker.health_updated.connect(health_updates.append)
    worker.error_occurred.connect(errors.append)
    worker._sleep_check = lambda _ms: worker.stop()

    worker.run()

    assert len(store.attempts) == 2
    assert store.attempts[0] is store.attempts[1]
    assert store.closed is True
    assert FakeListener.instances[0].started is True
    assert FakeListener.instances[0].stopped is True
    assert worker.health.status == "stopped"
    assert worker.health.last_sample_at is not None
    assert worker.health.last_persist_at is not None
    assert worker.health.pending_persists == 0
    assert worker.health.shutdown_safe is True
    assert "delayed" in [health.status for health in health_updates]
    assert errors and "database busy" in errors[0]


def test_run_reports_fatal_when_shutdown_recovery_spool_fails(
    monkeypatch,
    tmp_path,
):
    store = FakeStore([OSError("disk full")] * 10)
    _patch_run_dependencies(monkeypatch, store)
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"persistence_shutdown_retry_attempts": 2}},
        recovery_path=tmp_path / "recovery.json",
    )
    monkeypatch.setattr(
        worker._recovery_spool,
        "store_sessions",
        lambda _sessions: (_ for _ in ()).throw(OSError("spool full")),
    )
    errors = []
    worker.error_occurred.connect(errors.append)
    worker._sleep_check = lambda _ms: worker.stop()

    worker.run()

    assert len(store.attempts) == 3
    assert store.closed is True
    assert FakeListener.instances[0].stopped is True
    assert worker.health.status == "fatal"
    assert worker.health.pending_persists == 1
    assert worker.health.recovery_status == "failed"
    assert worker.health.shutdown_safe is False
    assert worker.health.error
    assert any("disk full" in error for error in errors)


def test_persistent_worker_failure_spools_tail_and_reports_recovery(
    monkeypatch,
    tmp_path,
):
    recovery_path = tmp_path / "worker-recovery.json"
    store = FakeStore([OSError("disk full")] * 100)
    _patch_run_dependencies(monkeypatch, store)
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"persistence_shutdown_retry_attempts": 2}},
        recovery_path=recovery_path,
    )
    worker._sleep_check = lambda _ms: worker.stop()

    worker.run()

    recovered = worker._recovery_spool.load_sessions()
    assert len(recovered) == 1
    assert recovered[0].session_id
    assert worker.health.status == "stopped"
    assert worker.health.pending_persists == 0
    assert worker.health.recovery_path == str(recovery_path)
    assert worker.health.recovery_status == "pending"
    assert worker.health.recovery_pending == 1
    assert worker.health.shutdown_safe is True
    assert store.closed is True


def test_listener_initialization_failure_still_closes_store(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(
        worker_module.classifier,
        "Classifier",
        lambda *_args: StaticClassifier(),
    )
    monkeypatch.setattr(
        worker_module,
        "SessionRuntimeStore",
        lambda _db_path: store,
    )
    monkeypatch.setattr(
        worker_module.keyboard,
        "Listener",
        lambda **_kwargs: (_ for _ in ()).throw(OSError("listener unavailable")),
    )
    monkeypatch.setattr(worker_module, "AudioDetector", None)
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    errors = []
    worker.error_occurred.connect(errors.append)

    worker.run()

    assert store.closed is True
    assert worker.health.status == "fatal"
    assert errors == ["listener unavailable"]


def test_persistence_retry_queue_is_bounded():
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"persistence_retry_queue_size": 1}},
    )
    worker._store = FakeStore([OSError("offline"), OSError("offline")])

    assert worker._persist_or_queue(_session("one")) is True

    with pytest.raises(RuntimeError, match="retry queue is full"):
        worker._persist_or_queue(_session("two"))

    assert worker.health.status == "fatal"
    assert worker.health.pending_persists == 1


def test_retry_boundary_attempts_only_one_fifo_session():
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"persistence_retry_queue_size": 2}},
    )
    store = FakeStore([OSError("offline"), OSError("offline")])
    worker._store = store
    worker._persist_or_queue(_session("one"))
    worker._persist_or_queue(_session("two"))

    worker._retry_pending_once()

    assert len(store.attempts) == 3
    assert list(worker._pending_persists) == ["two"]


def test_successful_retry_keeps_delayed_health_while_backlog_remains():
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"persistence_retry_queue_size": 2}},
    )
    store = FakeStore([OSError("offline"), OSError("offline")])
    worker._store = store
    first = _session("one")
    worker._persist_or_queue(first)
    worker._persist_or_queue(_session("two"))

    worker._persist_or_queue(first)

    assert list(worker._pending_persists) == ["two"]
    assert worker.health.status == "delayed"
    assert worker.health.pending_persists == 1


def test_cleanup_drains_full_queue_before_persisting_tail_session():
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {
            "tracker": {
                "persistence_retry_queue_size": 1,
                "persistence_shutdown_retry_attempts": 3,
            }
        },
    )
    store = FakeStore(
        [
            OSError("initial outage"),
            OSError("still offline"),
            None,
            None,
        ]
    )
    worker._store = store
    older = _session("older")
    tail = _session("tail")
    worker._persist_or_queue(older)
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=StaticClassifier(),
        on_session_end=worker._persist_or_queue,
    )
    tracker._current = tail
    worker._tracker = tracker

    worker._cleanup()

    assert tracker.current_session is None
    assert [session.session_id for session in store.attempts] == [
        "older",
        "older",
        "older",
        "tail",
    ]
    assert worker.health.status == "stopped"
    assert worker.health.pending_persists == 0
    assert store.closed is True


def test_cleanup_spools_retained_tail_when_full_queue_never_recovers(tmp_path):
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {
            "tracker": {
                "persistence_retry_queue_size": 1,
                "persistence_shutdown_retry_attempts": 1,
            }
        },
        recovery_path=tmp_path / "recovery.json",
    )
    store = FakeStore([OSError("offline")] * 10)
    worker._store = store
    worker._persist_or_queue(_session("older"))
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=StaticClassifier(),
        on_session_end=worker._persist_or_queue,
    )
    tracker._current = _session("tail")
    worker._tracker = tracker

    worker._cleanup()

    assert tracker.current_session is not None
    assert tracker.current_session.session_id == "tail"
    assert worker.health.status == "stopped"
    assert worker.health.pending_persists == 0
    assert worker.health.recovery_pending == 2
    assert worker.health.shutdown_safe is True
    assert store.closed is True


def test_worker_rewrite_adapter_hands_failure_to_bounded_persist_queue(
    monkeypatch,
):
    class RewriteOfflineStore(FakeStore):
        def __init__(self):
            super().__init__()
            self.rewrite_attempts = []

        def rewrite_session(self, session, *, busy_timeout_ms=None):
            self.rewrite_attempts.append((session, busy_timeout_ms))
            raise OSError("offline")

    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr(
        "daylens.session_tracker._get_keyboard_snapshot",
        lambda: bytes(256),
    )
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"persistence_retry_queue_size": 2}},
    )
    store = RewriteOfflineStore()
    worker._store = store
    assert worker._tracker_config()["tracker"][
        "attention_rewrite_queue_size"
    ] == 2
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
            }
        },
        classifier=StaticClassifier(),
        on_session_end=lambda _session: True,
        on_session_rewrite=worker._rewrite_or_queue,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 201,
    }
    notes = {
        "process_name": "Notes.exe",
        "window_title": "notes.md",
        "exe_path": "",
        "pid": 202,
    }

    tracker.tick(0, coding)
    old_session = tracker.current_session
    tracker.tick(0, notes)

    assert tracker.pending_rewrite_sessions() == ()
    assert list(worker._pending_persists) == [old_session.session_id]
    assert worker._pending_persists[old_session.session_id].rewrite is True
    assert [item[0] for item in store.rewrite_attempts] == [old_session]


def test_cleanup_spools_tracker_rewrites_and_tail_then_replays_all(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr(
        "daylens.session_tracker._get_keyboard_snapshot",
        lambda: bytes(256),
    )
    recovery_path = tmp_path / "attention-rewrites.json"
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "idle_threshold_seconds": 1,
            }
        },
        classifier=StaticClassifier(),
        on_session_end=lambda _session: True,
        on_session_rewrite=lambda _session: False,
    )
    coding = {
        "process_name": "Code.exe",
        "window_title": "main.py",
        "exe_path": "",
        "pid": 203,
    }
    notes = {
        "process_name": "Notes.exe",
        "window_title": "notes.md",
        "exe_path": "",
        "pid": 204,
    }
    tracker.tick(0, coding)
    rewritten_session = tracker.current_session
    tracker.tick(0, notes)
    tail = tracker.current_session
    assert tracker.pending_rewrite_sessions() == (rewritten_session,)

    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"persistence_shutdown_retry_attempts": 1}},
        recovery_path=recovery_path,
    )
    worker._tracker = tracker
    worker._store = FakeStore([OSError("offline")] * 10)

    worker._cleanup()

    recovered = worker._recovery_spool.load_sessions()
    assert [session.session_id for session in recovered] == [
        rewritten_session.session_id,
        tail.session_id,
    ]
    assert tracker.pending_rewrite_sessions() == ()
    replay_store = FakeStore()
    assert worker._recovery_spool.replay(replay_store) == 2
    assert [session.session_id for session in replay_store.attempts] == [
        rewritten_session.session_id,
        tail.session_id,
    ]
    assert worker._recovery_spool.load_sessions() == []


def test_invalid_settings_command_keeps_previous_tracker_state(monkeypatch):
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    tracker = TrackerStub()
    old_config = dict(worker.config)
    old_classifier = tracker.classifier
    worker._tracker = tracker
    errors = []
    worker.error_occurred.connect(errors.append)
    monkeypatch.setattr(
        worker_module.classifier,
        "Classifier",
        lambda *_args: (_ for _ in ()).throw(ValueError("bad rules")),
    )
    worker.update_settings(
        {"tracker": {"sample_interval_seconds": 9, "idle_threshold_seconds": 99}}
    )

    worker._consume_commands()

    assert worker.config == old_config
    assert worker.sample_interval == 1
    assert tracker.sample_interval == 1
    assert tracker.idle_threshold == 60
    assert tracker.classifier is old_classifier
    assert worker.health.status == "degraded"
    assert errors == ["bad rules"]


def test_successful_retry_does_not_overwrite_fatal_health():
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    store = FakeStore([OSError("offline")])
    worker._store = store
    session = _session("fatal-retry")
    worker._persist_or_queue(session)
    worker._mark_fatal(RuntimeError("queue overflow"))

    worker._persist_or_queue(session)

    assert worker.health.status == "fatal"
    assert worker.health.error == "queue overflow"
    assert worker.health.pending_persists == 0


@pytest.mark.parametrize("pending_count", [10, 100])
def test_shutdown_retry_budget_applies_to_each_pending_session(pending_count):
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {
            "tracker": {
                "persistence_retry_queue_size": pending_count,
                "persistence_shutdown_retry_attempts": 3,
            }
        },
    )
    store = PerSessionStore()
    worker._store = store
    sessions = [_session(f"session-{index}") for index in range(pending_count)]
    for session in sessions:
        worker._persist_or_queue(session)
    store.queueing = False
    initial_attempt_count = len(store.attempt_ids)

    worker._drain_pending_persists()

    assert list(worker._pending_persists) == []
    assert store.attempt_ids[initial_attempt_count:] == [
        session.session_id for session in sessions
    ]


def test_shutdown_drain_preserves_fifo_and_continues_after_item_exhausts_budget():
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {
            "tracker": {
                "persistence_retry_queue_size": 3,
                "persistence_shutdown_retry_attempts": 2,
            }
        },
    )
    store = PerSessionStore()
    worker._store = store
    for session_id in ("one", "two", "three"):
        worker._persist_or_queue(_session(session_id))
    store.queueing = False
    store.remaining_failures = {"one": 99, "two": 1}
    initial_attempt_count = len(store.attempt_ids)

    worker._drain_pending_persists()

    assert store.attempt_ids[initial_attempt_count:] == [
        "one",
        "two",
        "three",
        "one",
        "two",
    ]
    assert list(worker._pending_persists) == ["one"]
    assert worker._pending_persists["one"].attempts >= 3


def test_shutdown_drain_uses_one_deadline_and_fair_fifo_for_100_busy_sessions():
    class Clock:
        def __init__(self):
            self.now = 0.0

        def monotonic(self):
            return self.now

    class BusyStore:
        def __init__(self, clock):
            self.clock = clock
            self.queueing = True
            self.attempt_ids = []
            self.timeouts = []

        def persist_session(self, session, *, busy_timeout_ms=None):
            self.attempt_ids.append(session.session_id)
            if self.queueing:
                raise OSError("offline")
            self.timeouts.append(busy_timeout_ms)
            self.clock.now += 1.0
            raise OSError("still busy")

        def close(self):
            pass

    clock = Clock()
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {
            "tracker": {
                "persistence_retry_queue_size": 100,
                "persistence_shutdown_retry_attempts": 3,
                "persistence_shutdown_deadline_seconds": 5,
            }
        },
        monotonic_clock=clock.monotonic,
    )
    store = BusyStore(clock)
    worker._store = store
    for index in range(100):
        worker._persist_or_queue(_session(f"session-{index}"))
    store.queueing = False
    initial_attempts = len(store.attempt_ids)

    worker._drain_pending_persists()

    assert store.attempt_ids[initial_attempts:] == [
        f"session-{index}" for index in range(5)
    ]
    assert all(timeout <= 5_000 for timeout in store.timeouts)
    assert worker.shutdown_wait_budget_ms() <= 15_000


def test_cleanup_tail_persist_uses_remaining_global_deadline(tmp_path):
    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

    class BusyStore:
        def __init__(self):
            self.timeouts = []

        def persist_session(self, _session, *, busy_timeout_ms=None):
            self.timeouts.append(busy_timeout_ms)
            raise OSError("database busy")

        def close(self):
            pass

    clock = Clock()
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {
            "tracker": {
                "persistence_shutdown_deadline_seconds": 2,
                "persistence_shutdown_retry_attempts": 1,
            }
        },
        recovery_path=tmp_path / "recovery.json",
        monotonic_clock=clock.monotonic,
    )
    worker._store = BusyStore()
    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=StaticClassifier(),
        on_session_end=worker._persist_or_queue,
    )
    tracker._current = _session("tail")
    worker._tracker = tracker

    worker._cleanup()

    assert worker._store.timeouts[0] is not None
    assert worker._store.timeouts[0] <= 2_000


def test_live_queue_full_remains_recoverable_after_outer_run_catch(
    monkeypatch,
    tmp_path,
):
    first = _session("first")
    tail = _session("tail")
    store = FakeStore(
        [
            OSError("offline"),
            OSError("offline"),
            None,
            OSError("offline"),
            OSError("offline"),
        ]
    )
    _patch_run_dependencies(monkeypatch, store)

    class QueueFillingTracker:
        def __init__(self, *, on_session_end, **_kwargs):
            self.on_session_end = on_session_end
            self.current_session = None

        def tick(self, _idle_seconds, _window):
            self.current_session = first
            self.on_session_end(first)
            self.current_session = tail
            self.on_session_end(tail)

        def finish_current(self, reason):
            self.current_session.switch_reason = reason
            result = self.on_session_end(self.current_session)
            if result:
                self.current_session = None
            return result

        def mark_user_active(self):
            pass

    monkeypatch.setattr(worker_module, "SessionTracker", QueueFillingTracker)
    recovery_path = tmp_path / "recovery.json"
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {
            "tracker": {
                "persistence_retry_queue_size": 1,
                "persistence_shutdown_retry_attempts": 1,
            }
        },
        recovery_path=recovery_path,
    )
    worker._sleep_check = lambda _ms: worker.stop()

    worker.run()

    recovered = worker._recovery_spool.load_sessions()
    assert [session.session_id for session in recovered] == ["tail"]
    assert worker.health.status == "stopped"
    assert worker.health.recovery_status == "pending"
    assert worker.health.shutdown_safe is True


def test_repeated_sample_failures_report_delay_and_success_recovers():
    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

    clock = Clock()
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"sample_interval_seconds": 1}},
        monotonic_clock=clock.monotonic,
    )

    worker._record_sample_failure(RuntimeError("foreground unavailable"))
    assert worker.health.status == "degraded"

    clock.now = 5.0
    worker._record_sample_failure(RuntimeError("foreground unavailable"))
    assert worker.health.status == "sample_delayed"
    assert worker.health.last_sample_at is None

    worker._record_sample_success(datetime(2026, 7, 26, 10, 0, 0))
    assert worker.health.status == "running"
    assert worker.health.last_sample_at == datetime(2026, 7, 26, 10, 0, 0)
    assert worker.health.error == ""


def test_queue_full_fatal_becomes_safe_when_cleanup_persists_every_session():
    first = _session("first")
    tail = _session("tail")
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {
            "tracker": {
                "persistence_retry_queue_size": 1,
                "persistence_shutdown_retry_attempts": 1,
            }
        },
    )
    worker._store = FakeStore(
        [
            OSError("offline"),
            OSError("offline"),
            None,
            None,
        ]
    )

    assert worker._persist_or_queue(first) is True
    with pytest.raises(RuntimeError, match="retry queue is full"):
        worker._persist_or_queue(tail)

    tracker = SessionTracker(
        config={"tracker": {"min_session_seconds": 1}},
        classifier=StaticClassifier(),
        on_session_end=worker._persist_or_queue,
    )
    tracker._current = tail
    worker._tracker = tracker

    worker._cleanup()

    assert worker.health.status == "stopped"
    assert worker.health.pending_persists == 0
    assert worker.health.shutdown_safe is True
