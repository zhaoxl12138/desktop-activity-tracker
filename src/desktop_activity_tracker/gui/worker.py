"""Background recording worker running in a QThread."""

from datetime import datetime

from PySide6.QtCore import QThread, Signal

from .. import window_detector, activity_detector, classifier, database


class RecordingWorker(QThread):
    sample_updated = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, config_path, db_path, sample_interval):
        super().__init__()
        self.config_path = config_path
        self.db_path = db_path
        self.sample_interval = sample_interval
        self._running = True
        self._paused = False
        self._last_error = ""

    def run(self):
        clf = classifier.Classifier(self.config_path)
        conn = database.init_db(self.db_path)

        while self._running:
            if self._paused:
                self.msleep(1000)
                continue

            try:
                now = datetime.now()
                idle_sec = activity_detector.get_idle_seconds()
                win_info = window_detector.get_foreground_window_info()

                if win_info and (win_info.get("process_name") or win_info.get("window_title")):
                    cat = clf.classify(win_info.get("process_name", ""), win_info.get("window_title", ""))
                    is_effective = clf.is_effective(cat["active_rule"], idle_sec)
                    is_user_active = idle_sec <= clf.idle_threshold

                    sample = {
                        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "date": now.strftime("%Y-%m-%d"),
                        "process_name": win_info.get("process_name", ""),
                        "exe_path": win_info.get("exe_path", ""),
                        "window_title": win_info.get("window_title", ""),
                        "category_key": cat["category_key"],
                        "category_name": cat["category_name"],
                        "active_rule": cat["active_rule"],
                        "is_user_active": is_user_active,
                        "is_effective": is_effective,
                        "idle_seconds": round(idle_sec, 1),
                        "duration_seconds": self.sample_interval,
                    }
                else:
                    sample = {
                        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "date": now.strftime("%Y-%m-%d"),
                        "process_name": "system",
                        "exe_path": "",
                        "window_title": "idle/desktop",
                        "category_key": "other",
                        "category_name": "空闲",
                        "active_rule": "interactive_required",
                        "is_user_active": False,
                        "is_effective": False,
                        "idle_seconds": round(idle_sec, 1),
                        "duration_seconds": self.sample_interval,
                    }

                database.insert_activity_log(conn, sample)
                self.sample_updated.emit(sample)

                for _ in range(self.sample_interval):
                    if not self._running:
                        break
                    self.msleep(1000)

            except Exception as e:
                err_msg = str(e)
                if err_msg != self._last_error:
                    self._last_error = err_msg
                    self.error_occurred.emit(err_msg)
                self.msleep(self.sample_interval * 1000)

        conn.close()

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def is_paused(self):
        return self._paused
