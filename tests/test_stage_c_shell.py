from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker import database  # noqa: E402
from desktop_activity_tracker.gui.main_window import MainWindow, NAV_ITEMS  # noqa: E402
from desktop_activity_tracker.services import settings_service  # noqa: E402


class DummyWorker(QObject):
    sample_updated = Signal(dict)
    classification_history_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self._paused = False
        self.reload_intelligence_calls = 0
        self.reload_classifier_calls = 0

    def is_paused(self):
        return self._paused

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def update_settings(self, _config):
        return None

    def reload_intelligence(self):
        self.reload_intelligence_calls += 1

    def reload_classifier(self):
        self.reload_classifier_calls += 1

    def stop(self):
        return None

    def wait(self, _timeout=0):
        return True


def _window(*, legacy_task_settings=False):
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
    if legacy_task_settings:
        from daylens.services.intelligence_state import save_settings
        save_settings(root / "intelligence", {
            "task_analysis_enabled": True, "task_cloud_enabled": True,
        })
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
        "today", "stats", "rules", "reports", "settings"
    ]
    assert NAV_ITEMS[1][0] == "数据统计"
    stats = window.pages["stats"]
    assert isinstance(stats.tabs, QTabWidget)
    assert stats.tabs.widget(0) is window.pages["live"]
    assert stats.tabs.widget(1) is window.pages["software"]
    assert stats.tabs.widget(2) is window.pages["category"]
    window.navigate_to("stats", tab="software")
    app.processEvents()
    assert window._current_nav_key == "stats"
    assert stats.tabs.currentWidget() is window.pages["software"]
    window.close()


def test_sidebar_stats_reentry_defaults_live_but_explicit_navigation_keeps_target_tab():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    stats = window.pages["stats"]
    try:
        window.navigate_to("stats", tab="category")
        assert stats.tabs.currentWidget() is window.pages["category"]
        window.navigate_to("today")
        window.nav_list.setCurrentRow(1)  # Direct sidebar click.
        app.processEvents()
        assert stats.tabs.currentWidget() is window.pages["live"]
        assert window.lbl_page_title.text() == "实时监控"
        for tab in ("software", "category", "goals"):
            window.navigate_to("today")
            window.navigate_to("stats", tab=tab)
            app.processEvents()
            assert stats.tabs.currentWidget() is window.pages[tab]
    finally:
        window.close()


def test_task_analysis_entry_is_removed_even_with_legacy_switches():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window(legacy_task_settings=True)
    try:
        stats = window.pages["stats"]
        assert [stats.tabs.tabText(i) for i in range(stats.tabs.count())] == [
            "实时监控", "软件统计", "分类统计", "目标与成果",
        ]
        assert "tasks" not in window.pages
        window.navigate_to("stats", tab="goals")
        app.processEvents()
        assert stats.tabs.currentWidget() is window.pages["goals"]
        assert window.lbl_page_title.text() == "设置目标"
    finally:
        window.close()


def test_worker_ai_history_signal_refreshes_without_double_classifier_reload(
    monkeypatch,
):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    invalidations = []
    monkeypatch.setattr(
        window.dashboard_refresh, "invalidate_context",
        lambda: invalidations.append("dashboard"),
    )
    try:
        window.worker.classification_history_changed.emit({
            "updated_sessions": 1,
            "rule_changed": True,
            "classifier_reloaded": True,
        })
        app.processEvents()

        assert invalidations == ["dashboard"]
        assert window.worker.reload_classifier_calls == 0
    finally:
        window.close()


def test_dashboard_and_goal_refresh_never_enqueue_retired_task_analysis(monkeypatch):
    from desktop_activity_tracker.gui.dashboard_refresh_controller import DashboardSnapshot

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app, window = _window(legacy_task_settings=True)
    submitted = []
    monkeypatch.setattr(window.background_tasks, "submit",
                        lambda key, _work: submitted.append(key) or True)
    try:
        day = "2026-10-20"
        window._on_dashboard_snapshot(DashboardSnapshot(1, 1.0, {
            "today": day, "totals": {"effective_seconds": 120},
        }))
        window.pages["goals"].refresh_requested.emit(day)
        assert "goal:load:" + day in submitted
        assert not any(key.startswith("task:") for key in submitted)
        assert window.pages["today"].last_shell_summary["effective_seconds"] == 120
    finally:
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


def test_top_record_status_is_compact_and_vertically_centered():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    for width in (1280, 1920):
        window.resize(width, 720 if width == 1280 else 1080)
        app.processEvents()
        badge = window.top_record_status
        assert 28 <= badge.height() <= 36
        assert badge.parentWidget() is window._summary_capsule
        assert window._summary_capsule.rect().contains(badge.geometry())
        assert badge.width() >= max(80, badge.sizeHint().width())
        assert window.btn_pause.height() == 44
        assert not hasattr(window, "btn_report")
        assert not any(
            button.text() == "生成日报"
            for button in window._top_bar.findChildren(QPushButton)
        )
    window.close()


def test_report_center_remains_available_without_home_report_button():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app, window = _window()
    try:
        assert not hasattr(window, "btn_report")
        window.navigate_to("reports")
        assert window._current_nav_key == "reports"
        assert window.pages["reports"].isVisible()
    finally:
        window.close()


def test_recording_status_uses_readable_normal_weight_in_running_and_paused_states():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app, window = _window()
    try:
        window._update_recording_health_ui()
        assert "font-weight: 600" in window.sidebar_record_status.styleSheet()
        assert "font-weight: 600" in window.top_record_status.styleSheet()
        window._toggle_pause()
        assert "font-weight: 600" in window.sidebar_record_status.styleSheet()
        assert "font-weight: 600" in window.top_record_status.styleSheet()
    finally:
        window.close()


def test_live_tab_reuses_page_and_keeps_sample_routing_and_legacy_navigation(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    seen = []
    live = window.pages['live']
    monkeypatch.setattr(live, 'on_sample_updated', lambda sample: seen.append(sample))
    try:
        window._on_sample({'process_name': 'cached.exe'})
        window.navigate_to('live')
        app.processEvents()
        assert len(seen) == 1
        assert window._current_nav_key == 'stats'
        assert window.pages['stats'].tabs.currentWidget() is live
        assert window.lbl_page_title.text() == '实时监控'
        sample = {'process_name': 'synthetic.exe'}
        window._on_sample(sample)
        assert seen[-1] == sample
        window.navigate_to('stats', tab='software')
        assert window.lbl_page_title.text() == '数据统计'
        count = len(seen)
        window._on_sample({'process_name': 'hidden.exe'})
        assert len(seen) == count
        window.navigate_to('stats', tab='live')
        assert seen[-1]['process_name'] == 'hidden.exe'
        count = len(seen)
        window.navigate_to('stats', tab='software')
        window.navigate_to('stats', tab='live')
        assert len(seen) == count  # No new worker tick: do not duplicate cached history.
        window.navigate_to('settings')
        assert window.top_record_status.isVisible()
    finally:
        window.close()


def test_classification_correction_reloads_rules_and_invalidates_statistics(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app, window = _window()
    invalidated = []
    rules_reloaded = []
    monkeypatch.setattr(
        window.dashboard_refresh,
        "invalidate_context",
        lambda: invalidated.append("dashboard"),
    )
    monkeypatch.setattr(
        window.pages["software"]._refresh_controller,
        "invalidate_context",
        lambda: invalidated.append("software"),
    )
    monkeypatch.setattr(
        window.pages["category"]._refresh_controller,
        "invalidate_context",
        lambda: invalidated.append("category"),
    )
    monkeypatch.setattr(
        window.pages["rules"].rules_editor,
        "reload_from_storage",
        lambda: rules_reloaded.append(True) or True,
    )
    try:
        window.pages["live"].classification_corrected.emit()
        window.pages["live"].classification_history_changed.emit({
            "updated_sessions": 6,
            "rule_changed": True,
            "shared_browser": False,
        })
        assert window.worker.reload_intelligence_calls == 1
        assert window.worker.reload_classifier_calls == 1
        assert invalidated == ["dashboard", "software", "category"]
        assert rules_reloaded == [True]
    finally:
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


def test_both_day_cards_open_one_read_only_dialog_in_snapshot_date_range(monkeypatch):
    from types import SimpleNamespace
    from desktop_activity_tracker.gui import main_window as module
    from desktop_activity_tracker.gui.widgets.day_activity_dialog import DayActivityDialog

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, window = _window()
    days = [f"2026-10-{day:02d}" for day in range(19, 26)]
    opened = []

    def create(db, day, dates, **kwargs):
        dialog = DayActivityDialog(db, day, dates, loader=lambda *_a, **_k: {
            "day": day, "status": "empty", "events": [], "segments": [],
        }, **kwargs)
        opened.append(dialog)
        return dialog

    monkeypatch.setattr(module, "DayActivityDialog", create)
    window._dashboard_snapshot = SimpleNamespace(payload={
        "rhythm": {"7d": {"chart": {"dates": days}}},
    })
    try:
        window.pages["today"].rhythm_card.day_activated.emit(days[1])
        assert len(opened) == 1
        assert opened[0].day_picker.currentData() == days[1]
        window.pages["today"].entertainment_history_card.day_activated.emit(days[3])
        assert len(opened) == 1
        assert opened[0].day_picker.currentData() == days[3]
        assert [opened[0].day_picker.itemData(i) for i in range(7)] == days
        window.pages["today"].rhythm_card.day_activated.emit("2020-01-01")
        assert len(opened) == 1
        assert "tasks" not in window.pages
    finally:
        for dialog in opened:
            dialog.close()
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
