from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QApplication, QTabWidget

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker import database  # noqa: E402
from desktop_activity_tracker.gui.main_window import MainWindow, NAV_ITEMS  # noqa: E402
from desktop_activity_tracker.services import settings_service  # noqa: E402


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

    def update_settings(self, _config):
        return None

    def stop(self):
        return None

    def wait(self, _timeout=0):
        return True


def _window():
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    config_path = root / "config.yaml"
    db_path = root / "usage.db"
    reports = root / "reports"
    reports.mkdir()
    config = {
        "theme": "dark",
        "db_path": str(db_path),
        "reports_dir": str(reports),
        "categories": {},
        "show_home_poetry": False,
    }
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    database.init_db(str(db_path)).close()
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        str(root), config, str(db_path), str(config_path), str(reports), DummyWorker()
    )
    window._stage_c_temp = temp
    window.show()
    app.processEvents()
    window.dashboard_refresh.shutdown(timeout_ms=1_000)
    return app, window


def test_navigation_merges_statistics_without_recreating_existing_pages():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    assert [key for _title, key, _hint in NAV_ITEMS] == [
        "today", "stats", "rules", "reports", "settings", "live"
    ]
    stats = window.pages["stats"]
    assert isinstance(stats.tabs, QTabWidget)
    assert stats.tabs.widget(0) is window.pages["software"]
    assert stats.tabs.widget(1) is window.pages["category"]
    window.navigate_to("stats", tab="software")
    app.processEvents()
    assert window._current_nav_key == "stats"
    assert stats.tabs.currentWidget() is window.pages["software"]
    window.close()


def test_top_bar_has_one_primary_metric_and_no_category_capsule_wall():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    assert set(window.capsule_values) == {"total"}
    assert window.capsule_labels["total"].text() == "有效活动"
    assert len(window.summary_capsule_items) == 1
    assert window._top_bar.minimumHeight() <= 112
    assert window._top_bar.maximumHeight() <= 128
    assert window.sidebar_record_status.text() in {
        "记录中", "已暂停", "正在保存", "记录异常", "待恢复"
    }
    window.close()


def test_today_layout_switches_by_content_width_and_preserves_card_instances():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    page = window.pages["today"]
    cards = (
        page.distribution_card,
        page.rhythm_card,
        page.entertainment_history_card,
        page.work_analysis_card,
        page.top_app_card,
    )
    page.set_content_width(1200)
    assert page.layout_mode == "wide"
    page.set_content_width(1000)
    assert page.layout_mode == "compact"
    page.set_content_width(800)
    assert page.layout_mode == "single"
    assert cards == (
        page.distribution_card,
        page.rhythm_card,
        page.entertainment_history_card,
        page.work_analysis_card,
        page.top_app_card,
    )
    assert page._card_grid.itemAtPosition(0, 0).widget() is page.distribution_card
    assert page._card_grid.itemAtPosition(1, 0).widget() is page.rhythm_card
    assert page._card_grid.itemAtPosition(2, 0).widget() is page.entertainment_history_card
    assert page._card_grid.itemAtPosition(4, 0).widget() is page.top_app_card
    assert page._card_grid.itemAtPosition(5, 0) is None
    assert not hasattr(page, "action_card")
    window.close()


def test_work_analysis_uses_neutral_switch_wording_and_content_height():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app, window = _window()
    page = window.pages["today"]
    texts = {label.text() for label in page.interruption_card.findChildren(type(page.interruption_card.conclusion_label))}
    assert "工作切换" in texts
    assert "明显切换" in texts
    assert "切换累计" in texts
    assert page.work_analysis_card.sizePolicy().verticalPolicy().name in {"Preferred", "Maximum"}
    window.close()


def test_top_app_shortcut_opens_software_statistics():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    window.pages["today"].top_app_card.activated.emit()
    app.processEvents()
    assert window._current_nav_key == "stats"
    assert window.pages["stats"].tabs.currentWidget() is window.pages["software"]
    window.close()


def test_today_header_does_not_echo_current_app_category():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    assert not window.lbl_page_hint.isVisible()

    window._on_sample({"category_name": "工作学习", "engaged_seconds": 72})
    app.processEvents()
    assert not window.lbl_page_hint.isVisible()
    assert window.lbl_page_hint.textFormat() == Qt.PlainText

    window._toggle_pause()
    assert not window.lbl_page_hint.isVisible()
    window.navigate_to("settings")
    app.processEvents()
    assert not window.lbl_page_hint.isVisible()
    window.navigate_to("today")
    app.processEvents()
    assert not window.lbl_page_hint.isVisible()
    window.close()


def test_today_header_shows_only_cached_ai_observation():
    from datetime import date
    from types import SimpleNamespace
    from desktop_activity_tracker.services.intelligence_privacy import privacy_revision
    from desktop_activity_tracker.services.intelligence_state import atomic_json, load_settings, save_settings

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    directory = window.paths.intelligence_dir
    save_settings(directory, {"enabled": True, "reports_enabled": True,
                              "monthly_budget_micros": 4_000_000})
    day = date.today().isoformat()
    settings = load_settings(directory)
    atomic_json(directory / "observations" / f"{day}.json", {
        "status": "ready", "day": day, "version": 1,
        "privacy_revision": privacy_revision(settings),
        "text": "今天工作被明显打断4次", "as_of": "14:50",
    })
    window._dashboard_snapshot = SimpleNamespace(payload={"today": day})
    window._show_daily_observation()
    app.processEvents()
    assert window.lbl_page_hint.isVisible()
    assert window.lbl_page_hint.fullText() == "AI观察 · 截至14:50 · 今天工作被明显打断4次"
    assert "今天工作被明显打断4次" in window.lbl_page_hint.toolTip()
    window._on_sample({"category_name": "系统工具", "process_name": "DayLens.exe"})
    assert "系统工具" not in window.lbl_page_hint.text()
    window.navigate_to("settings")
    app.processEvents()
    assert not window.lbl_page_hint.isVisible()
    window.close()


def test_retired_poetry_setting_is_removed_on_next_save(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    database.save_settings(str(db_path), {"show_home_poetry": True})
    monkeypatch.setattr(settings_service, "save_user_config", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(settings_service, "load_user_config", lambda: {})
    updated = settings_service.save_page_config(
        config_path=str(tmp_path / "config.yaml"),
        db_path=str(db_path),
        config={"theme": "dark", "db_path": str(db_path), "show_home_poetry": True},
        sample_interval=1,
        idle_threshold=60,
        startup_enabled=False,
        new_db_path=str(db_path),
        obsidian_output_path="",
    )
    assert "show_home_poetry" not in updated
    loaded = settings_service.load_page_config(str(tmp_path / "missing.yaml"), str(db_path))
    assert "show_home_poetry" not in loaded
    assert "show_home_poetry" not in (database.load_settings(str(db_path)) or {})


def test_settings_page_has_no_poetry_control():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app, window = _window()
    assert not hasattr(window.pages["settings"], "chk_home_poetry")
    window.close()
