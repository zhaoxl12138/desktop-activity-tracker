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
        self.classifier = object()
        self.active_marks = 0

    def mark_user_active(self):
        self.active_marks += 1


class StaticClassifier:
    def classify(self, _process_name, _window_title):
        return {
            "category_key": "coding",
            "category_name": "Coding",
            "active_rule": "interactive_required",
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


def test_worker_control_state_uses_threading_events():
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    event_type = type(threading.Event())

    assert isinstance(worker._running, event_type)
    assert isinstance(worker._paused, event_type)
    assert isinstance(worker._pause_requested, event_type)


def test_settings_update_is_applied_only_when_worker_consumes_command(monkeypatch):
    worker = worker_module.RecordingWorker("config.yaml", "usage.db", {})
    tracker = TrackerStub()
    worker._tracker = tracker
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
    assert tracker.classifier is replacement_classifier
    assert worker.sample_interval == 3


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
    assert construction_threads == [threading.get_ident()]


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
    assert "delayed" in [health.status for health in health_updates]
    assert errors and "database busy" in errors[0]


def test_run_reports_fatal_when_shutdown_retry_cannot_persist(monkeypatch):
    store = FakeStore([OSError("disk full")] * 10)
    _patch_run_dependencies(monkeypatch, store)
    worker = worker_module.RecordingWorker(
        "config.yaml",
        "usage.db",
        {"tracker": {"persistence_shutdown_retry_attempts": 2}},
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
    assert worker.health.error
    assert any("disk full" in error for error in errors)


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


def test_cleanup_counts_retained_tail_when_full_queue_never_recovers():
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
    assert worker.health.status == "fatal"
    assert worker.health.pending_persists == 2
    assert store.closed is True


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
        "one",
        "two",
        "two",
        "three",
    ]
    assert list(worker._pending_persists) == ["one"]
    assert worker._pending_persists["one"].attempts >= 3
