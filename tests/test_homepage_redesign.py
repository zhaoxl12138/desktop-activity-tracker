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
    sample_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self._paused = False

    def is_paused(self):
        return self._paused

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def update_settings(self, config):
        return None

    def stop(self):
        return None

    def wait(self, timeout=0):
        return True


def _write_config(path: Path):
    config = {
        "theme": "dark",
        "db_path": str(path.parent / "usage.db"),
        "reports_dir": str(path.parent / "reports"),
        "obsidian_output_path": "",
        "tracker": {
            "sample_interval_seconds": 1,
            "flush_interval_seconds": 5,
            "idle_threshold_seconds": 60,
            "min_session_seconds": 2,
        },
        "categories": {
            "coding": {
                "display_name": "编程开发",
                "active_rule": "interactive_required",
                "match": {"process_names": ["Code.exe"], "title_keywords": []},
            },
            "tools": {
                "display_name": "系统工具",
                "active_rule": "interactive_required",
                "match": {"process_names": ["DayLens.exe"], "title_keywords": []},
            },
            "other": {
                "display_name": "其他",
                "active_rule": "interactive_required",
                "match": {"process_names": [], "title_keywords": []},
            },
        },
    }
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return config


def test_homepage_shell_matches_reference_structure():
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
        window = MainWindow(
            str(tmp_path),
            config,
            str(db_path),
            str(config_path),
            str(reports_dir),
            DummyWorker(),
        )
        window.show()
        app.processEvents()

        assert window.size().width() == 1600
        assert window.size().height() == 900
        assert window.minimumSize() == window.maximumSize()
        assert set(window.capsule_values) == {"total", "work", "ent", "social"}
        assert window.capsule_labels["total"].text() == "活跃时间"
        assert window.capsule_labels["work"].text() == "工作学习"
        assert window.capsule_labels["ent"].text() == "娱乐休闲"
        assert window.capsule_icons["ent"].text() == "📺"
        assert window.capsule_labels["social"].text() == "社交通讯"
        assert not hasattr(window, "bottom_bar")
        assert window.pages["today"].metric_cards == {}
        assert window.pages["today"].time_stats_ratio_ring is not None

        window.close()
