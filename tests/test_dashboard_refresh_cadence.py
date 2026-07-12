from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QCoreApplication
import yaml
from PySide6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker import database  # noqa: E402
from desktop_activity_tracker.gui.pages.today_overview import TodayOverviewPage  # noqa: E402
from desktop_activity_tracker.gui.worker import RecordingWorker  # noqa: E402


def test_config_flushes_activity_every_five_seconds():
    config = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))

    assert config["tracker"]["flush_interval_seconds"] == 5


def test_worker_default_flush_interval_matches_dashboard_refresh():
    worker = RecordingWorker("config.yaml", "usage.db", {})

    assert worker.flush_interval == 5


def test_today_overview_refreshes_every_five_seconds(tmp_path):
    app = QApplication.instance() or QApplication([])
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))

    page = TodayOverviewPage(str(db_path))

    assert page.timer.interval() == 5000
    assert page.timer.isActive() is False
    page.deleteLater()
    app.processEvents()


def test_today_overview_only_refreshes_after_activation(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    calls = {"count": 0}

    def fake_snapshot(_db_path, _resolver):
        calls["count"] += 1
        return {
            "today": "2026-06-06",
            "stats": {},
            "totals": {
                "effective_seconds": 0,
                "idle_seconds": 0,
                "total_seconds": 0,
                "active_ratio": 0,
            },
            "distribution_sections": [],
            "day_comparison": {
                "work": {"direction": "empty", "delta_seconds": 0},
                "entertainment": {"direction": "empty", "delta_seconds": 0},
                "social": {"direction": "empty", "delta_seconds": 0},
            },
            "sessions": [],
            "focus_summary": "今日暂未识别到连续专注时段。",
            "consecutive_days": 0,
            "top_app_rows": [],
            "trend": {"today": [0] * 24, "yesterday": [0] * 24, "seven_days": [[0] * 24 for _ in range(7)], "thirty_days": [0] * 30},
        }

    monkeypatch.setattr("desktop_activity_tracker.gui.pages.today_overview.load_today_snapshot", fake_snapshot)

    page = TodayOverviewPage(str(db_path))

    assert calls["count"] == 0
    page.activate(force=True)
    QCoreApplication.processEvents()
    app.processEvents()
    assert calls["count"] == 1
    assert page.timer.isActive() is True

    page.deactivate()
    assert page.timer.isActive() is False
    page.deleteLater()
    app.processEvents()


def test_today_overview_exposes_shell_summary_from_same_snapshot(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))

    def fake_snapshot(_db_path, _resolver):
        return {
            "today": "2026-06-06",
            "stats": {},
            "totals": {"effective_seconds": 420, "idle_seconds": 30, "total_seconds": 450, "active_ratio": 93},
            "distribution_sections": [
                {"category_key": "work", "label": "工作学习", "seconds": 240},
                {"category_key": "video", "label": "娱乐休闲", "seconds": 120},
                {"category_key": "social", "label": "社交通讯", "seconds": 60},
            ],
            "day_comparison": {}, "sessions": [], "focus_summary": "", "consecutive_days": 0,
            "top_app_rows": [],
            "trend": {"today": [0] * 24, "yesterday": [0] * 24, "seven_days": [[0] * 24 for _ in range(7)], "thirty_days": [0] * 30},
        }

    monkeypatch.setattr("desktop_activity_tracker.gui.pages.today_overview.load_today_snapshot", fake_snapshot)
    page = TodayOverviewPage(str(db_path))
    page.activate(force=True)
    app.processEvents()

    assert page.last_shell_summary == {
        "effective_seconds": 420,
        "work_seconds": 240,
        "entertainment_seconds": 120,
        "social_seconds": 60,
    }
    page.deleteLater()
    app.processEvents()
