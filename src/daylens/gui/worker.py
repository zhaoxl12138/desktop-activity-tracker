"""Background recording worker running in a QThread with SessionTracker."""

from __future__ import annotations

import copy
import queue
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from pynput import keyboard

from .. import activity_detector, classifier, window_detector
from ..services.session_recovery_service import SessionRecoverySpool
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
    recovery_pending: int = 0
    recovery_path: str = ""
    recovery_status: str = "none"
    shutdown_safe: bool = False


@dataclass
class _PendingPersist:
    session: object
    attempts: int = 0
    error: str = ""
    rewrite: bool = False


class _PersistenceQueueFull(RuntimeError):
    pass


class _FixedSamplingCadence:
    """Keep sampling on a monotonic deadline without burst catch-up."""

    def __init__(self, monotonic_clock):
        self._clock = monotonic_clock
        self._deadline = self._clock()

    def reset(self) -> None:
        self._deadline = self._clock()

    def next_sleep_ms(self, interval_seconds: float) -> int:
        interval = max(0.001, float(interval_seconds))
        self._deadline += interval
        now = self._clock()
        remaining = self._deadline - now
        if -remaining >= interval:
            self._deadline = now
            return 0
        return max(0, int(round(remaining * 1000)))


class RecordingWorker(QThread):
    _PERSISTENCE_BUSY_TIMEOUT_MS = 5_000
    _SHUTDOWN_WAIT_MARGIN_MS = 1_000

    sample_updated = Signal(dict)
    error_occurred = Signal(str)
    health_updated = Signal(object)

    def __init__(
        self,
        config_path,
        db_path,
        config,
        *,
        recovery_path=None,
        monotonic_clock=None,
    ):
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
        self._recoverable_fatal = False
        self._health_lock = threading.Lock()
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._sampling_cadence = _FixedSamplingCadence(self._monotonic_clock)
        self._sample_health_started_at = self._monotonic_clock()
        self._last_sample_monotonic = None
        self._shutdown_deadline = None
        self._recovery_spool = SessionRecoverySpool(
            db_path,
            recovery_path=recovery_path,
        )
        recovery_exists = self._recovery_spool.path.exists()
        self._health = RecordingHealth(
            status="starting",
            recovery_pending=1 if recovery_exists else 0,
            recovery_path=str(self._recovery_spool.path),
            recovery_status="pending" if recovery_exists else "none",
        )

        self._load_worker_settings(self.config)

    @property
    def health(self) -> RecordingHealth:
        with self._health_lock:
            return self._health

    def shutdown_wait_budget_ms(self) -> int:
        """Return a conservative bound for cleanup persistence attempts."""

        return min(
            15_000,
            int(self._shutdown_deadline_seconds * 1000)
            + self._SHUTDOWN_WAIT_MARGIN_MS,
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
            "_shutdown_deadline_seconds": min(
                14.0,
                max(
                    0.0,
                    float(
                        tracker_cfg.get(
                            "persistence_shutdown_deadline_seconds",
                            10,
                        )
                    ),
                ),
            ),
            "_degraded_after_attempts": max(
                1, int(tracker_cfg.get("persistence_degraded_after_attempts", 3))
            ),
        }

    def _pending_persist_count(self) -> int:
        session_ids = set(self._pending_persists)
        session_ids.update(
            session.session_id for session in self._tracker_pending_rewrites()
        )
        if self._retained_tail is not None:
            session_ids.add(self._persistence_key(self._retained_tail))
        return len(session_ids)

    def _tracker_pending_rewrites(self) -> tuple:
        snapshot = getattr(self._tracker, "pending_rewrite_sessions", None)
        return tuple(snapshot()) if callable(snapshot) else ()

    def _drain_tracker_rewrites(self) -> bool:
        drain = getattr(self._tracker, "drain_pending_rewrites", None)
        return bool(drain()) if callable(drain) else True

    def _set_health(
        self,
        status: str | None = None,
        *,
        last_sample_at: datetime | None = None,
        last_persist_at: datetime | None = None,
        error: str | None = None,
        recovery_pending: int | None = None,
        recovery_status: str | None = None,
        shutdown_safe: bool | None = None,
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
            if recovery_pending is not None:
                updates["recovery_pending"] = max(0, int(recovery_pending))
            if recovery_status is not None:
                updates["recovery_status"] = recovery_status
            if shutdown_safe is not None:
                updates["shutdown_safe"] = bool(shutdown_safe)
            self._health = replace(self._health, **updates)
            snapshot = self._health
        self.health_updated.emit(snapshot)

    def _report_error(self, error, status: str) -> None:
        message = str(error) or error.__class__.__name__
        if message != self._last_error:
            self._last_error = message
            self.error_occurred.emit(message)
        self._set_health(status, error=message)

    def _mark_fatal(self, error, *, recoverable: bool = False) -> None:
        self._fatal = True
        self._recoverable_fatal = recoverable
        self._running.clear()
        self._report_error(error, "fatal")
        self._set_health(shutdown_safe=False)

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
                "attention_rewrite_queue_size": tracker.get(
                    "attention_rewrite_queue_size",
                    self._max_pending_persists,
                ),
            }
        }

    def run(self):
        self._set_health("starting", error="")
        try:
            clf = classifier.Classifier(self.config_path, self.db_path)
            self._store = SessionRuntimeStore(self.db_path)
            try:
                replayed = self._recovery_spool.replay(self._store)
            except Exception:
                self._set_health(
                    recovery_pending=1,
                    recovery_status="failed",
                    shutdown_safe=False,
                )
                raise
            self._set_health(
                recovery_pending=0,
                recovery_status="replayed" if replayed else "none",
            )
            tracker_config = self._tracker_config()
            tracker_options = tracker_config["tracker"]
            self._tracker = SessionTracker(
                config=tracker_config,
                classifier=clf,
                on_session_end=self._persist_or_queue,
                on_flush=self._persist_or_queue,
                on_session_rewrite=self._rewrite_or_queue,
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
            self._sampling_cadence.reset()

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
                    self._sampling_cadence.reset()
                    continue

                try:
                    idle_sec = activity_detector.get_idle_seconds()
                    win_info = window_detector.get_foreground_window_info()
                    snapshot = self._tracker.tick(idle_sec, win_info)
                    if snapshot is not None:
                        sampled_at = datetime.now()
                        self.sample_updated.emit(snapshot)
                        self._record_sample_success(sampled_at)
                except _PersistenceQueueFull:
                    raise
                except Exception as error:
                    self._record_sample_failure(error)

                self._sleep_check(
                    self._sampling_cadence.next_sleep_ms(self.sample_interval)
                )
        except Exception as error:
            # Queue exhaustion is recoverable once cleanup has durably
            # transferred every unresolved session to the recovery spool.
            self._mark_fatal(error, recoverable=self._recoverable_fatal)
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        self._shutdown_deadline = (
            self._monotonic_clock() + self._shutdown_deadline_seconds
        )
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception as error:
                self._mark_fatal(error)

        if self._store is not None:
            # Make room before handing off the tail session. Otherwise a full
            # queue can retain the tail in SessionTracker with no later retry.
            self._drain_pending_persists()
            had_tracker_rewrites = bool(self._tracker_pending_rewrites())
            try:
                self._drain_tracker_rewrites()
            except Exception as error:
                self._report_error(error, "degraded")
            if had_tracker_rewrites:
                self._drain_pending_persists()

        if self._tracker is not None and self._tracker.current_session is not None:
            tail = self._tracker.current_session
            if self._remaining_shutdown_ms() <= 0:
                self._retained_tail = tail
            else:
                try:
                    if self._tracker.finish_current("shutdown"):
                        self._retained_tail = None
                    else:
                        self._retained_tail = tail
                except Exception as error:
                    self._retained_tail = tail
                    self._report_error(error, "degraded")

        if self._store is not None:
            self._drain_pending_persists()
            had_tracker_rewrites = bool(self._tracker_pending_rewrites())
            try:
                self._drain_tracker_rewrites()
            except Exception as error:
                self._report_error(error, "degraded")
            if had_tracker_rewrites:
                self._drain_pending_persists()

            # A queue-full tail stays owned by SessionTracker. If draining made
            # room, hand it off now and give it the same bounded retry budget.
            if (
                self._retained_tail is not None
                and len(self._pending_persists) < self._max_pending_persists
                and self._remaining_shutdown_ms() > 0
            ):
                try:
                    if self._tracker.finish_current("shutdown"):
                        self._retained_tail = None
                    self._drain_pending_persists()
                except Exception as error:
                    self._report_error(error, "degraded")

            if self._pending_persist_count():
                self._spool_unresolved()
            try:
                self._store.close()
            except Exception as error:
                self._mark_fatal(error)

        if self._recoverable_fatal and not self._pending_persist_count():
            self._fatal = False
            self._recoverable_fatal = False

        shutdown_safe = self._pending_persist_count() == 0
        if not self._fatal:
            self._set_health("stopped", error="", shutdown_safe=True)
        else:
            self._set_health(shutdown_safe=shutdown_safe)
        self._shutdown_deadline = None

    def _record_sample_success(self, sampled_at: datetime) -> None:
        self._last_sample_monotonic = self._monotonic_clock()
        if self._pending_persists:
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
            status = "running"
            error = ""
            self._last_error = ""
        self._set_health(
            status,
            last_sample_at=sampled_at,
            error=error,
        )

    def _record_sample_failure(self, error) -> None:
        last_success = (
            self._last_sample_monotonic
            if self._last_sample_monotonic is not None
            else self._sample_health_started_at
        )
        elapsed = max(0.0, self._monotonic_clock() - last_success)
        delay_threshold = max(5.0, float(self.sample_interval) * 3.0)
        status = "sample_delayed" if elapsed >= delay_threshold else "degraded"
        self._report_error(error, status)

    def _spool_unresolved(self) -> None:
        rewrites = self._tracker_pending_rewrites()
        sessions_by_id = OrderedDict(
            (self._persistence_key(item.session), item.session)
            for item in self._pending_persists.values()
        )
        for session in rewrites:
            sessions_by_id[self._persistence_key(session)] = session
        if self._retained_tail is not None:
            sessions_by_id[self._persistence_key(self._retained_tail)] = (
                self._retained_tail
            )
        try:
            stored_count = self._recovery_spool.store_sessions(
                sessions_by_id.values()
            )
        except Exception as error:
            self._set_health(recovery_status="failed", shutdown_safe=False)
            self._mark_fatal(error)
            return

        self._pending_persists.clear()
        self._retained_tail = None
        acknowledge = getattr(
            self._tracker,
            "acknowledge_pending_rewrites",
            None,
        )
        if callable(acknowledge):
            acknowledge(session.session_id for session in rewrites)
        if self._recoverable_fatal:
            self._fatal = False
            self._recoverable_fatal = False
        self._set_health(
            recovery_pending=stored_count,
            recovery_status="pending",
        )

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

    def _persist_or_queue(
        self,
        session,
        *,
        busy_timeout_ms: int | None = None,
        rewrite: bool = False,
    ) -> bool:
        if self._store is None:
            raise RuntimeError("session store is not initialized")
        if busy_timeout_ms is None and self._shutdown_deadline is not None:
            busy_timeout_ms = min(
                self._PERSISTENCE_BUSY_TIMEOUT_MS,
                self._remaining_shutdown_ms(),
            )
        key = self._persistence_key(session)
        try:
            result = self._call_persist(
                session,
                busy_timeout_ms=busy_timeout_ms,
                rewrite=rewrite,
            )
            self._validate_persist_result(result)
        except Exception as error:
            pending = self._pending_persists.get(key)
            if pending is None:
                if len(self._pending_persists) >= self._max_pending_persists:
                    queue_error = _PersistenceQueueFull(
                        "session persistence retry queue is full"
                    )
                    self._mark_fatal(queue_error, recoverable=True)
                    raise queue_error from error
                pending = _PendingPersist(session=session, rewrite=rewrite)
                self._pending_persists[key] = pending
            else:
                pending.session = session
                pending.rewrite = pending.rewrite or rewrite
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

    def _rewrite_or_queue(self, session) -> bool:
        """Hand an idempotent session_id rewrite to the bounded worker queue."""
        return self._persist_or_queue(session, rewrite=True)

    def _retry_pending_once(self) -> None:
        if not self._pending_persists:
            return
        pending = next(iter(self._pending_persists.values()))
        self._persist_or_queue(
            pending.session,
            rewrite=pending.rewrite,
        )

    def _call_persist(
        self,
        session,
        *,
        busy_timeout_ms: int | None,
        rewrite: bool = False,
    ):
        persist = (
            self._store.rewrite_session
            if rewrite
            else self._store.persist_session
        )
        if busy_timeout_ms is None:
            return persist(session)
        try:
            return persist(
                session,
                busy_timeout_ms=busy_timeout_ms,
            )
        except TypeError as error:
            if "busy_timeout_ms" not in str(error):
                raise
            return persist(session)

    def _remaining_shutdown_ms(self, deadline=None) -> int:
        effective_deadline = (
            self._shutdown_deadline if deadline is None else deadline
        )
        if effective_deadline is None:
            return self._PERSISTENCE_BUSY_TIMEOUT_MS
        return max(
            0,
            int((effective_deadline - self._monotonic_clock()) * 1000),
        )

    def _drain_pending_persists(self) -> None:
        if not self._pending_persists or self._shutdown_retry_attempts <= 0:
            return
        deadline = self._shutdown_deadline
        if deadline is None:
            deadline = (
                self._monotonic_clock() + self._shutdown_deadline_seconds
            )
        keys = list(self._pending_persists)
        attempts_by_key = {key: 0 for key in keys}
        total_budget = len(keys) * self._shutdown_retry_attempts
        total_attempts = 0
        while keys and total_attempts < total_budget:
            remaining_ms = self._remaining_shutdown_ms(deadline)
            if remaining_ms <= 0:
                break
            key = keys.pop(0)
            pending = self._pending_persists.get(key)
            if pending is None:
                continue
            self._persist_or_queue(
                pending.session,
                busy_timeout_ms=min(
                    self._PERSISTENCE_BUSY_TIMEOUT_MS,
                    remaining_ms,
                ),
                rewrite=pending.rewrite,
            )
            total_attempts += 1
            attempts_by_key[key] += 1
            if (
                key in self._pending_persists
                and attempts_by_key[key] < self._shutdown_retry_attempts
            ):
                keys.append(key)

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
                        if not self._tracker.replace_classifier(
                            replacement_classifier
                        ):
                            raise RuntimeError(
                                "classifier replacement could not finish "
                                "current session"
                            )
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

        if not self._tracker.replace_classifier(replacement_classifier):
            raise RuntimeError(
                "classifier replacement could not finish current session"
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
        self._tracker._max_pending_attention_rewrites = max(
            1,
            int(
                tracker_cfg.get(
                    "attention_rewrite_queue_size",
                    self._max_pending_persists,
                )
            ),
        )
        self._sampling_cadence.reset()

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
