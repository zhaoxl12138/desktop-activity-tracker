"""Background recording worker running in a QThread with SessionTracker."""

from __future__ import annotations

import copy
import queue
import threading
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from pynput import keyboard

from .. import activity_detector, classifier, window_detector
from ..services.session_runtime_service import SessionRuntimeStore
from ..session_tracker import SessionTracker

try:
    from ..audio_detector import AudioDetector
except Exception:  # Optional dependency; startup must not fail without it.
    AudioDetector = None


@dataclass(frozen=True)
class RecordingHealth:
    """Immutable worker health snapshot safe for GUI-thread consumption."""

    status: str
    last_sample_at: datetime | None = None
    last_persist_at: datetime | None = None
    error: str = ""
    pending_persists: int = 0


@dataclass
class _PendingPersist:
    session: object
    attempts: int = 0
    error: str = ""


class _PersistenceQueueFull(RuntimeError):
    pass


class RecordingWorker(QThread):
    _PERSISTENCE_BUSY_TIMEOUT_MS = 5_000
    _SHUTDOWN_WAIT_MARGIN_MS = 1_000

    sample_updated = Signal(dict)
    error_occurred = Signal(str)
    health_updated = Signal(object)

    def __init__(self, config_path, db_path, config):
        super().__init__()
        self.config_path = config_path
        self.db_path = db_path
        self.config = copy.deepcopy(config)

        self._running = threading.Event()
        self._running.set()
        self._paused = threading.Event()
        self._pause_requested = threading.Event()
        self._keyboard_activity = threading.Event()
        self._commands: queue.Queue[tuple[str, object]] = queue.Queue()

        self._tracker = None
        self._store = None
        self._listener = None
        self._pending_persists: OrderedDict[str, _PendingPersist] = OrderedDict()
        self._retained_tail = None
        self._last_error = ""
        self._fatal = False
        self._health_lock = threading.Lock()
        self._health = RecordingHealth(status="starting")

        self._load_worker_settings(self.config)

    @property
    def health(self) -> RecordingHealth:
        with self._health_lock:
            return self._health

    def shutdown_wait_budget_ms(self) -> int:
        """Return a conservative bound for cleanup persistence attempts."""

        pending_count = max(0, int(self.health.pending_persists))
        retry_attempts = max(0, int(self._shutdown_retry_attempts))
        # One item may currently be inside persistence and the current tracker
        # session can become a second tail item after stop(). Cleanup has two
        # drain phases plus final handoff/close operations.
        possible_items = pending_count + 2
        blocking_calls = (2 * possible_items * retry_attempts) + 4
        return (
            blocking_calls * self._PERSISTENCE_BUSY_TIMEOUT_MS
            + self._SHUTDOWN_WAIT_MARGIN_MS
        )

    def _load_worker_settings(self, config) -> None:
        settings = self._worker_settings(config)
        for name, value in settings.items():
            setattr(self, name, value)

    @staticmethod
    def _worker_settings(config) -> dict[str, object]:
        tracker_cfg = config.get("tracker", {})
        return {
            "sample_interval": tracker_cfg.get(
                "sample_interval_seconds",
                config.get("sample_interval_seconds", 1),
            ),
            "flush_interval": tracker_cfg.get(
                "flush_interval_seconds",
                config.get("flush_interval_seconds", 5),
            ),
            "_max_pending_persists": max(
                1, int(tracker_cfg.get("persistence_retry_queue_size", 100))
            ),
            "_shutdown_retry_attempts": max(
                0, int(tracker_cfg.get("persistence_shutdown_retry_attempts", 3))
            ),
            "_degraded_after_attempts": max(
                1, int(tracker_cfg.get("persistence_degraded_after_attempts", 3))
            ),
        }

    def _pending_persist_count(self) -> int:
        return len(self._pending_persists) + (
            1 if self._retained_tail is not None else 0
        )

    def _set_health(
        self,
        status: str | None = None,
        *,
        last_sample_at: datetime | None = None,
        last_persist_at: datetime | None = None,
        error: str | None = None,
    ) -> None:
        with self._health_lock:
            updates = {"pending_persists": self._pending_persist_count()}
            if status is not None:
                updates["status"] = status
            if last_sample_at is not None:
                updates["last_sample_at"] = last_sample_at
            if last_persist_at is not None:
                updates["last_persist_at"] = last_persist_at
            if error is not None:
                updates["error"] = error
            self._health = replace(self._health, **updates)
            snapshot = self._health
        self.health_updated.emit(snapshot)

    def _report_error(self, error, status: str) -> None:
        message = str(error) or error.__class__.__name__
        if message != self._last_error:
            self._last_error = message
            self.error_occurred.emit(message)
        self._set_health(status, error=message)

    def _mark_fatal(self, error) -> None:
        self._fatal = True
        self._running.clear()
        self._report_error(error, "fatal")

    def _tracker_config(self) -> dict:
        tracker = self.config.get("tracker", {})
        return {
            "tracker": {
                "sample_interval_seconds": self.sample_interval,
                "flush_interval_seconds": self.flush_interval,
                "idle_threshold_seconds": tracker.get(
                    "idle_threshold_seconds",
                    self.config.get("idle_threshold_seconds", 60),
                ),
                "entertainment_idle_threshold_seconds": tracker.get(
                    "entertainment_idle_threshold_seconds", 300
                ),
                "min_session_seconds": tracker.get(
                    "min_session_seconds",
                    self.config.get("min_session_seconds", 2),
                ),
                "cross_group_grace_seconds": tracker.get(
                    "cross_group_grace_seconds", 30
                ),
            }
        }

    def run(self):
        self._set_health("starting", error="")
        try:
            clf = classifier.Classifier(self.config_path, self.db_path)
            self._store = SessionRuntimeStore(self.db_path)
            tracker_config = self._tracker_config()
            tracker_options = tracker_config["tracker"]
            self._tracker = SessionTracker(
                config=tracker_config,
                classifier=clf,
                on_session_end=self._persist_or_queue,
                on_flush=self._persist_or_queue,
                audio_detector=(
                    AudioDetector(
                        check_interval=self.config.get("tracker", {}).get(
                            "audio_check_interval_seconds", 3.0
                        )
                    )
                    if AudioDetector is not None
                    else None
                ),
            )
            # Keep the public interval values sourced from the exact tracker config.
            self.sample_interval = tracker_options["sample_interval_seconds"]
            self.flush_interval = tracker_options["flush_interval_seconds"]

            self._listener = keyboard.Listener(on_press=self._on_key_press)
            self._listener.daemon = True
            self._listener.start()
            self._set_health("running")

            while self._running.is_set():
                self._consume_commands()
                self._consume_keyboard_activity()
                self._retry_pending_once()

                if self._pause_requested.is_set():
                    if self._tracker.current_session is not None:
                        self._tracker.finish_current("paused")
                    self._pause_requested.clear()
                if self._paused.is_set():
                    self._sleep_check(1000)
                    continue

                try:
                    idle_sec = activity_detector.get_idle_seconds()
                    win_info = window_detector.get_foreground_window_info()
                    snapshot = self._tracker.tick(idle_sec, win_info)
                    if snapshot is not None:
                        sampled_at = datetime.now()
                        self.sample_updated.emit(snapshot)
                        status = (
                            self.health.status
                            if self._pending_persists
                            else "running"
                        )
                        self._set_health(status, last_sample_at=sampled_at)
                except _PersistenceQueueFull:
                    raise
                except Exception as error:
                    self._report_error(error, "degraded")

                self._sleep_check(int(self.sample_interval * 1000))
        except Exception as error:
            self._mark_fatal(error)
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception as error:
                self._mark_fatal(error)

        if self._store is not None:
            # Make room before handing off the tail session. Otherwise a full
            # queue can retain the tail in SessionTracker with no later retry.
            self._drain_pending_persists()

        if self._tracker is not None and self._tracker.current_session is not None:
            tail = self._tracker.current_session
            try:
                if self._tracker.finish_current("shutdown"):
                    self._retained_tail = None
                else:
                    self._retained_tail = tail
            except Exception as error:
                self._retained_tail = tail
                self._mark_fatal(error)

        if self._store is not None:
            self._drain_pending_persists()

            # A queue-full tail stays owned by SessionTracker. If draining made
            # room, hand it off now and give it the same bounded retry budget.
            if (
                self._retained_tail is not None
                and len(self._pending_persists) < self._max_pending_persists
            ):
                try:
                    if self._tracker.finish_current("shutdown"):
                        self._retained_tail = None
                    self._drain_pending_persists()
                except Exception as error:
                    self._mark_fatal(error)

            if self._pending_persist_count():
                self._mark_fatal(
                    RuntimeError(
                        f"{self._pending_persist_count()} session(s) remain "
                        "unpersisted after shutdown retries"
                    )
                )
            try:
                self._store.close()
            except Exception as error:
                self._mark_fatal(error)

        if not self._fatal:
            self._set_health("stopped")

    @staticmethod
    def _persistence_key(session) -> str:
        session_id = getattr(session, "session_id", "")
        return str(session_id) if session_id else f"object:{id(session)}"

    @staticmethod
    def _validate_persist_result(result) -> None:
        if result is None or result is False:
            raise RuntimeError("session persistence did not report success")
        if isinstance(result, int) and result <= 0:
            raise RuntimeError(
                f"session persistence returned invalid row id {result}"
            )

    def _persist_or_queue(self, session) -> bool:
        if self._store is None:
            raise RuntimeError("session store is not initialized")
        key = self._persistence_key(session)
        try:
            result = self._store.persist_session(session)
            self._validate_persist_result(result)
        except Exception as error:
            pending = self._pending_persists.get(key)
            if pending is None:
                if len(self._pending_persists) >= self._max_pending_persists:
                    queue_error = _PersistenceQueueFull(
                        "session persistence retry queue is full"
                    )
                    self._mark_fatal(queue_error)
                    raise queue_error from error
                pending = _PendingPersist(session=session)
                self._pending_persists[key] = pending
            else:
                pending.session = session
            pending.attempts += 1
            pending.error = str(error)
            status = (
                "degraded"
                if pending.attempts >= self._degraded_after_attempts
                else "delayed"
            )
            self._report_error(error, status)
            # Ownership has moved to the retry queue, so SessionTracker may
            # safely release the ended session while this reference remains.
            return True

        self._pending_persists.pop(key, None)
        if self._fatal:
            status = "fatal"
            error = self.health.error
        elif self._pending_persists:
            status = (
                "degraded"
                if any(
                    item.attempts >= self._degraded_after_attempts
                    for item in self._pending_persists.values()
                )
                else "delayed"
            )
            error = self.health.error
        else:
            status = "paused" if self._paused.is_set() else "running"
            error = ""
            self._last_error = ""
        self._set_health(
            status,
            last_persist_at=datetime.now(),
            error=error,
        )
        return True

    def _retry_pending_once(self) -> None:
        if not self._pending_persists:
            return
        pending = next(iter(self._pending_persists.values()))
        self._persist_or_queue(pending.session)

    def _drain_pending_persists(self) -> None:
        for key in list(self._pending_persists):
            for _ in range(self._shutdown_retry_attempts):
                pending = self._pending_persists.get(key)
                if pending is None:
                    break
                self._persist_or_queue(pending.session)

    def _on_key_press(self, _key) -> None:
        self._keyboard_activity.set()

    def _consume_keyboard_activity(self) -> None:
        if not self._keyboard_activity.is_set():
            return
        self._keyboard_activity.clear()
        if self._tracker is not None:
            self._tracker.mark_user_active()

    def _consume_commands(self) -> None:
        while True:
            try:
                command, payload = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                if command == "settings":
                    self._apply_settings(payload)
                elif command == "reload_classifier":
                    if self._tracker is not None:
                        replacement_classifier = classifier.Classifier(
                            self.config_path, self.db_path
                        )
                        self._tracker.classifier = replacement_classifier
            except Exception as error:
                self._report_error(error, "degraded")

    def _apply_settings(self, config) -> None:
        replacement_config = copy.deepcopy(config)
        replacement_settings = self._worker_settings(replacement_config)
        if self._tracker is None:
            self.config = replacement_config
            for name, value in replacement_settings.items():
                setattr(self, name, value)
            return
        tracker_cfg = replacement_config.get("tracker", {})
        replacement_classifier = classifier.Classifier(
            self.config_path, self.db_path
        )
        idle_threshold = tracker_cfg.get(
            "idle_threshold_seconds",
            replacement_config.get("idle_threshold_seconds", 60),
        )
        entertainment_idle_threshold = tracker_cfg.get(
            "entertainment_idle_threshold_seconds", 300
        )
        min_session = tracker_cfg.get(
            "min_session_seconds",
            replacement_config.get("min_session_seconds", 2),
        )
        cross_group_grace = tracker_cfg.get(
            "cross_group_grace_seconds", 30
        )

        # All fallible work above has completed. Publish the new settings as
        # one worker-thread transaction so readers never see a partial update.
        self.config = replacement_config
        for name, value in replacement_settings.items():
            setattr(self, name, value)
        self._tracker.idle_threshold = idle_threshold
        self._tracker.entertainment_idle_threshold = (
            entertainment_idle_threshold
        )
        self._tracker.min_session = min_session
        self._tracker.cross_group_grace = cross_group_grace
        self._tracker.sample_interval = self.sample_interval
        self._tracker.flush_interval = self.flush_interval
        self._tracker.classifier = replacement_classifier

    def _sleep_check(self, ms):
        """Sleep in short chunks so stop() is responsive."""
        if ms <= 0:
            return
        chunk = 200
        remaining = ms
        while self._running.is_set() and remaining > 0:
            self.msleep(min(chunk, remaining))
            remaining -= chunk

    def update_settings(self, config):
        """Queue hot-reload settings for application in the worker thread."""
        self._commands.put(("settings", copy.deepcopy(config)))

    def reload_classifier(self):
        """Queue rule reload for application in the worker thread."""
        self._commands.put(("reload_classifier", None))

    def pause(self):
        self._pause_requested.set()
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def stop(self):
        self._running.clear()

    def is_paused(self):
        return self._paused.is_set()
