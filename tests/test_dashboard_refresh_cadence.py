from __future__ import annotations

from pathlib import Path
import sys

import yaml
from PySide6.QtWidgets import QApplication


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker import database  # noqa: E402
from daylens.gui.dashboard_refresh_controller import DashboardRefreshController  # noqa: E402
from desktop_activity_tracker.gui.pages.today_overview import TodayOverviewPage  # noqa: E402
from desktop_activity_tracker.gui.worker import RecordingWorker  # noqa: E402


def test_config_flushes_activity_every_five_seconds():
    config = yaml.safe_load((ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))

    assert config["tracker"]["flush_interval_seconds"] == 5


def test_worker_default_flush_interval_matches_dashboard_refresh():
    worker = RecordingWorker("config.yaml", "usage.db", {})

    assert worker.flush_interval == 5


def test_dashboard_controller_refreshes_every_five_seconds():
    controller = DashboardRefreshController(lambda: {})

    assert controller.timer.interval() == 5000
    assert controller.timer.isActive() is False
    assert controller.shutdown() is True


def test_today_overview_activation_never_starts_its_own_database_timer(tmp_path):
    app = QApplication.instance() or QApplication([])
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))

    page = TodayOverviewPage(str(db_path))

    page.activate(force=True)
    app.processEvents()
    assert page._is_active is True
    assert not hasattr(page, "timer")

    page.deactivate()
    assert page._is_active is False
    page.deleteLater()
    app.processEvents()


def test_today_overview_exposes_shell_summary_from_same_snapshot(tmp_path):
    app = QApplication.instance() or QApplication([])
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))

    snapshot = {
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
    page = TodayOverviewPage(str(db_path))
    page.apply_snapshot(snapshot)
    app.processEvents()

    assert page.last_shell_summary == {
        "effective_seconds": 420,
        "work_seconds": 240,
        "entertainment_seconds": 120,
        "social_seconds": 60,
    }
    page.deleteLater()
    app.processEvents()
