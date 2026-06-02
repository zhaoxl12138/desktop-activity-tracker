from __future__ import annotations

from pathlib import Path
import sys

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
    page.deleteLater()
    app.processEvents()
