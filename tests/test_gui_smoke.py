"""GUI smoke checks for the PySide6 dashboard shell.

Run manually:
    python tests/test_gui_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker import database  # noqa: E402
from desktop_activity_tracker.gui.main_window import MainWindow  # noqa: E402


class DummyWorker(QObject):
    """Minimal worker double used to exercise MainWindow interactions."""

    sample_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self._paused = False
        self.settings_updated = False

    def is_paused(self):
        return self._paused

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def update_settings(self, config):
        self.settings_updated = True

    def stop(self):
        return None

    def wait(self, timeout=0):
        return True


def _write_config(path: Path):
    config = {
        "db_path": str(path.parent / "usage.db"),
        "reports_dir": str(path.parent / "reports"),
        "obsidian_output_path": "",
        "tracker": {
            "sample_interval_seconds": 1,
            "flush_interval_seconds": 10,
            "idle_threshold_seconds": 60,
            "min_session_seconds": 2,
        },
        "categories": {
            "coding": {
                "display_name": "Coding",
                "active_rule": "interactive_required",
                "match": {"process_names": ["Code.exe"], "title_keywords": []},
            },
            "other": {
                "display_name": "Other",
                "active_rule": "interactive_required",
                "match": {"process_names": [], "title_keywords": []},
            },
        },
    }
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return config


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        config = _write_config(config_path)
        db_path = tmp_path / "usage.db"
        database.init_db(str(db_path)).close()

        app = QApplication.instance() or QApplication([])
        worker = DummyWorker()
        window = MainWindow(
            str(tmp_path),
            config,
            str(db_path),
            str(config_path),
            str(reports_dir),
            worker,
        )
        window.show()
        app.processEvents()

        assert window.width() >= 1280, f"default width too small: {window.width()}"
        assert window.height() >= 780, f"default height too small: {window.height()}"
        assert window.stack.count() == 6, f"unexpected page count: {window.stack.count()}"

        for row in range(window.nav_list.count()):
            item = window.nav_list.item(row)
            if item is not None and item.flags():
                window.nav_list.setCurrentRow(row)
                app.processEvents()

        worker_state_before = worker.is_paused()
        window.btn_pause.click()
        app.processEvents()
        assert worker.is_paused() is (not worker_state_before)
        window.btn_pause.click()
        app.processEvents()
        assert worker.is_paused() is worker_state_before

        screenshot = tmp_path / "dashboard-smoke.png"
        assert window.grab().save(str(screenshot)), "failed to save dashboard screenshot"
        assert screenshot.stat().st_size > 0, "dashboard screenshot is empty"

        window.close()
        print("GUI smoke test passed")


if __name__ == "__main__":
    main()
