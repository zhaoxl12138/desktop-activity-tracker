"""Background recording worker running in a QThread with SessionTracker."""

from datetime import datetime

from PySide6.QtCore import QThread, Signal

from .. import window_detector, activity_detector, classifier, database
from ..session_tracker import SessionTracker

try:
    from ..audio_detector import AudioDetector
except Exception:  # Optional dependency; startup must not fail without it.
    AudioDetector = None


class RecordingWorker(QThread):
    sample_updated = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, config_path, db_path, config):
        super().__init__()
        self.config_path = config_path
        self.db_path = db_path
        self.config = config
        self._running = True
        self._paused = False
        self._last_error = ""

        tracker_cfg = config.get("tracker", {})
        self.sample_interval = tracker_cfg.get("sample_interval_seconds",
            config.get("sample_interval_seconds", 1))
        self.flush_interval = tracker_cfg.get("flush_interval_seconds",
            config.get("flush_interval_seconds", 5))

    def run(self):
        clf = classifier.Classifier(self.config_path)
        conn = database.init_db(self.db_path)

        def on_session_end(session):
            try:
                if session._db_row_id > 0:
                    database.update_session(conn, session)
                else:
                    session._db_row_id = database.insert_session(conn, session)
            except Exception as e:
                import sys, traceback
                print(f"[Worker] insert_session error: {e}", file=sys.stderr)
                traceback.print_exc()

        def on_flush(session):
            try:
                if session._db_row_id > 0:
                    database.update_session(conn, session)
                else:
                    session._db_row_id = database.insert_session(conn, session)
            except Exception as e:
                import sys, traceback
                print(f"[Worker] flush error: {e}", file=sys.stderr)
                traceback.print_exc()

        tracker_cfg = {
            "tracker": {
                "sample_interval_seconds": self.sample_interval,
                "flush_interval_seconds": self.flush_interval,
                "idle_threshold_seconds":
                    self.config.get("tracker", {}).get("idle_threshold_seconds",
                        self.config.get("idle_threshold_seconds", 60)),
                "min_session_seconds":
                    self.config.get("tracker", {}).get("min_session_seconds", 2),
            }
        }

        self._tracker = SessionTracker(
            config=tracker_cfg,
            classifier=clf,
            on_session_end=on_session_end,
            on_flush=on_flush,
            audio_detector=(
                AudioDetector(
                    check_interval=self.config.get("tracker", {}).get(
                        "audio_check_interval_seconds", 3.0)
                )
                if AudioDetector is not None
                else None
            ),
        )
        tracker = self._tracker

        while self._running:
            if self._paused:
                self._sleep_check(1000)
                continue

            try:
                idle_sec = activity_detector.get_idle_seconds()
                win_info = window_detector.get_foreground_window_info()

                snapshot = tracker.tick(idle_sec, win_info)

                if snapshot is not None:
                    self.sample_updated.emit(snapshot)

            except Exception as e:
                err_msg = str(e)
                if err_msg != self._last_error:
                    self._last_error = err_msg
                    self.error_occurred.emit(err_msg)

            self._sleep_check(int(self.sample_interval * 1000))

        # Flush final session on shutdown
        sess = tracker.current_session
        if sess is not None and sess.duration_seconds >= tracker.min_session:
            sess.switch_reason = "shutdown"
            on_session_end(sess)

        database.close_db(conn)

    def _sleep_check(self, ms):
        """Sleep in short chunks so stop() is responsive."""
        if ms <= 0:
            return
        chunk = 200
        remaining = ms
        while self._running and remaining > 0:
            self.msleep(min(chunk, remaining))
            remaining -= chunk

    def update_settings(self, config):
        """Hot-reload settings from config without restart."""
        tracker_cfg = config.get("tracker", {})
        self.sample_interval = tracker_cfg.get("sample_interval_seconds",
            config.get("sample_interval_seconds", 1))
        self.flush_interval = tracker_cfg.get("flush_interval_seconds",
            config.get("flush_interval_seconds", 5))
        if hasattr(self, '_tracker') and self._tracker is not None:
            self._tracker.idle_threshold = tracker_cfg.get("idle_threshold_seconds",
                config.get("idle_threshold_seconds", 60))
            self._tracker.min_session = tracker_cfg.get("min_session_seconds",
                config.get("min_session_seconds", 2))
            self._tracker.sample_interval = self.sample_interval
            self._tracker.flush_interval = self.flush_interval
            self._tracker.classifier = classifier.Classifier(self.config_path)

    def reload_classifier(self):
        """Reload classification rules from config — pick up rule edits without restart."""
        if hasattr(self, '_tracker') and self._tracker is not None:
            self._tracker.classifier = classifier.Classifier(self.config_path)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False

    def is_paused(self):
        return self._paused
