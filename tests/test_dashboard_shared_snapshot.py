from __future__ import annotations

import os
import time
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import yaml
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from daylens import database
from daylens.gui import main_window
from daylens.gui.dashboard_refresh_controller import DashboardSnapshot


class RecordingWorker(QObject):
    sample_updated = Signal(dict)

    def is_paused(self):
        return False

    def pause(self):
        pass

    def resume(self):
        pass

    def update_settings(self, _config):
        pass

    def stop(self):
        pass

    def wait(self, _timeout=0):
        return True


class FakeRefreshController(QObject):
    snapshot_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, loader, *, interval_ms=5_000, parent=None):
        super().__init__(parent)
        self.loader = loader
        self.interval_ms = interval_ms
        self.foreground_calls = []
        self.shutdown_calls = 0

    def set_foreground(self, foreground):
        self.foreground_calls.append(bool(foreground))

    def request_refresh(self):
        pass

    def shutdown(self, timeout_ms=5_000):
        self.shutdown_calls += 1
        return True


def _snapshot_payload() -> dict[str, object]:
    return {
        "today": date.today().strftime("%Y-%m-%d"),
        "stats": {},
        "totals": {
            "effective_seconds": 420,
            "idle_seconds": 30,
            "total_seconds": 450,
            "active_ratio": 93,
        },
        "distribution_sections": [
            {"category_key": "work", "label": "工作学习", "seconds": 240},
            {"category_key": "video", "label": "娱乐休闲", "seconds": 120},
            {"category_key": "social", "label": "社交通讯", "seconds": 60},
        ],
        "day_comparison": {
            "work": {"direction": "up", "delta_seconds": 60},
            "entertainment": {"direction": "flat", "delta_seconds": 0},
            "social": {"direction": "down", "delta_seconds": -60},
        },
        "sessions": [],
        "focus_summary": "今日暂无连续专注时段",
        "consecutive_days": 3,
        "recording_streak_days": 81,
        "top_app_rows": [],
        "trend": {
            "today": [0] * 24,
            "today_work": [0] * 24,
            "today_entertainment": [0] * 24,
            "yesterday": [0] * 24,
            "yesterday_work": [0] * 24,
            "yesterday_entertainment": [0] * 24,
            "seven_days": [[0] * 24 for _ in range(7)],
            "seven_day_labels": [],
            "thirty_days": [0] * 30,
        },
    }


def test_main_window_uses_one_shared_background_snapshot(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    config = {
        "theme": "dark",
        "db_path": str(db_path),
        "obsidian_output_path": "",
        "tracker": {"sample_interval_seconds": 1, "idle_threshold_seconds": 60},
        "categories": {},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(
        main_window,
        "DashboardRefreshController",
        FakeRefreshController,
        raising=False,
    )
    window = main_window.MainWindow(
        str(tmp_path),
        config,
        str(db_path),
        str(config_path),
        str(tmp_path / "reports"),
        RecordingWorker(),
    )

    assert not hasattr(window.pages["today"], "timer")
    window.show()
    app.processEvents()
    assert window.dashboard_refresh.foreground_calls[-1] is True

    window.dashboard_refresh.snapshot_ready.emit(
        DashboardSnapshot(1, time.time(), _snapshot_payload())
    )
    app.processEvents()

    assert window.pages["today"].last_snapshot_totals["effective_seconds"] == 420
    assert window.capsule_values["total"].text() == "7分0秒"
    assert window.capsule_values["work"].text() == "4分0秒"
    assert "7分" in window.sidebar_record_value.text()
    assert window.sidebar_record_streak.text() == "连续记录：第81天"

    window.hide()
    app.processEvents()
    assert window.dashboard_refresh.foreground_calls[-1] is False
    window.deleteLater()
    app.processEvents()
