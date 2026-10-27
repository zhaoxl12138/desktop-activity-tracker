"""Selected-range category statistics retain the existing effective-time metric."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget, QWidget

from daylens.gui.pages.category_stats import CategoryStatsPage
from daylens.gui.pages.statistics import StatisticsPage
from daylens import database
from daylens.services import category_stats_service
from daylens.session_tracker import ActivitySession
from daylens.utils import ENTERTAINMENT_CATEGORY_KEYS, WORK_CATEGORY_KEYS, fmt_seconds


@pytest.mark.parametrize(
    ("bucket", "expected_keys"),
    [
        ("work", WORK_CATEGORY_KEYS),
        ("entertainment", ENTERTAINMENT_CATEGORY_KEYS),
    ],
)
def test_single_day_detail_expands_buckets_from_shared_registry(
    monkeypatch, bucket, expected_keys,
):
    observed = []

    def query(_db_path, _date_str, category_key, _limit):
        observed.append(category_key)
        return []

    monkeypatch.setattr(category_stats_service.database, "query_category_detail", query)

    category_stats_service.load_category_detail(
        "usage.db", "2026-10-27", bucket, limit=5,
    )

    assert set(observed) == set(expected_keys)


def test_statistics_opens_live_monitor_by_default_and_keeps_explicit_tabs():
    app = QApplication.instance() or QApplication([])
    software, category, live = QWidget(), QWidget(), QWidget()
    page = StatisticsPage(software, category, live_page=live)
    assert page.tabs.currentWidget() is live
    page.select_tab("category")
    assert page.tabs.currentWidget() is category
    page.select_tab("software")
    assert page.tabs.currentWidget() is software
    page.deleteLater()
    app.processEvents()


def test_range_summary_uses_one_inclusive_query_and_existing_category_merge(monkeypatch):
    observed = []

    def query(db_path, dates):
        observed.append((db_path, dates))
        return {
            "by_category": [
                {"category_key": "coding", "category_name": "工作学习", "effective_seconds": 120},
                {"category_key": "reading", "category_name": "阅读学习", "effective_seconds": 180},
                {"category_key": "video", "category_name": "娱乐休闲", "effective_seconds": 60},
            ]
        }

    monkeypatch.setattr(category_stats_service.database, "query_date_range_stats", query)
    result = category_stats_service.load_category_summary("usage.db", "2026-10-20", "2026-10-22")
    assert observed == [("usage.db", ["2026-10-20", "2026-10-21", "2026-10-22"])]
    assert result["range_start"] == "2026-10-20"
    assert result["range_end"] == "2026-10-22"
    assert [(row["category_key"], row["effective_seconds"]) for row in result["categories"]] == [
        ("work", 300), ("entertainment", 60)
    ]
    assert result["total_effective_seconds"] == 360


@pytest.mark.parametrize("start,end", [
    ("2026-10-23", "2026-10-22"),
    ("2026-10-01", "2027-10-02"),
    ("2026-13-01", "2026-10-02"),
])
def test_range_summary_rejects_invalid_or_unbounded_period(start, end):
    with pytest.raises(ValueError):
        category_stats_service.load_category_summary("unused.db", start, end)


def test_category_page_defaults_to_seven_days_and_switches_presets(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    today = QDate.currentDate()
    assert page._selected_range() == (today.addDays(-6).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd"))
    page.period_combo.setCurrentIndex(page.period_combo.findData("today"))
    assert page._selected_range() == (today.toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd"))
    assert page.start_edit.date() == today
    page.period_combo.setCurrentIndex(page.period_combo.findData("30d"))
    assert page._selected_range() == (today.addDays(-29).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd"))
    assert page.start_edit.date() == today.addDays(-29)
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def test_custom_range_is_inclusive_validated_and_invalidates_pending_results(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    previous = page._refresh_controller.latest_generation
    page.period_combo.setCurrentIndex(page.period_combo.findData("custom"))
    page.start_edit.setDate(QDate(2026, 10, 20))
    page.end_edit.setDate(QDate(2026, 10, 22))
    assert page._selected_range() == ("2026-10-20", "2026-10-22")
    assert page._refresh_controller.latest_generation > previous
    page.start_edit.setDate(QDate(2026, 10, 23))
    assert page.error_lbl.isHidden() is False
    with pytest.raises(ValueError):
        page._selected_range()
    page.start_edit.setDate(QDate(2025, 1, 1))
    assert page.error_lbl.isHidden() is False
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def test_category_page_uses_selected_range_for_summary_and_expanded_detail(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    seen = []
    monkeypatch.setattr(category_stats_service, "load_category_summary", lambda db, start, end: seen.append(("summary", start, end)) or {
        "today": end, "range_start": start, "range_end": end,
        "categories": [{"category_key": "work", "category_name": "工作学习", "effective_seconds": 60}],
        "total_effective_seconds": 60, "total_label": "range total",
    })
    monkeypatch.setattr(category_stats_service, "load_category_range_detail", lambda db, start, end, key, limit: seen.append(("detail", start, end, key, limit)) or [])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page.period_combo.setCurrentIndex(page.period_combo.findData("custom"))
    page.start_edit.setDate(QDate(2026, 10, 20))
    page.end_edit.setDate(QDate(2026, 10, 22))
    page._is_active = True
    page.refresh()
    page._expand_card("work")
    _wait_for(app, lambda: len(seen) == 2 and page._detail_refresh_controller._worker is None)
    assert seen == [
        ("summary", "2026-10-20", "2026-10-22"),
        ("detail", "2026-10-20", "2026-10-22", "work", 5),
    ]
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def test_background_summary_loader_uses_captured_selection_not_qt_widgets(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    seen = []
    monkeypatch.setattr(category_stats_service, "load_category_summary", lambda db, start, end: seen.append((start, end)) or {})
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page.period_combo.setCurrentIndex(page.period_combo.findData("custom"))
    page.start_edit.setDate(QDate(2026, 10, 20))
    page.end_edit.setDate(QDate(2026, 10, 22))
    monkeypatch.setattr(page, "_selected_range", lambda: (_ for _ in ()).throw(AssertionError("worker read UI")))
    page._load_selected_summary()
    assert seen == [("2026-10-20", "2026-10-22")]
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def test_expanded_category_shows_read_failure_instead_of_no_records(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary({
        "today": "2026-10-26", "range_start": "2026-10-20", "range_end": "2026-10-26",
        "categories": [{"category_key": "work", "category_name": "工作学习", "effective_seconds": 60}],
        "total_effective_seconds": 60, "total_label": "范围总计",
    })
    def fail(*_args):
        raise RuntimeError("synthetic read failure")
    monkeypatch.setattr(category_stats_service, "load_category_range_detail", fail)
    page._is_active = True
    page._expand_card("work")
    _wait_for(app, lambda: page._detail_refresh_controller._worker is None)
    texts = [label.text() for label in page._cards["work"]._detail.findChildren(QLabel)]
    assert any("读取失败" in text for text in texts)
    assert not any("暂无记录" in text for text in texts)
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def test_expanded_category_shows_read_failure_when_exception_message_is_empty(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary({
        "today": "2026-10-26", "range_start": "2026-10-20", "range_end": "2026-10-26",
        "categories": [{"category_key": "work", "category_name": "工作学习", "effective_seconds": 60}],
        "total_effective_seconds": 60, "total_label": "范围总计",
    })

    def fail(*_args):
        raise RuntimeError()

    monkeypatch.setattr(category_stats_service, "load_category_range_detail", fail)
    page._is_active = True
    page._expand_card("work")
    _wait_for(app, lambda: page._detail_refresh_controller._worker is None)
    texts = [label.text() for label in page._cards["work"]._detail.findChildren(QLabel)]
    assert any("读取失败" in text for text in texts)
    assert not any("暂无记录" in text for text in texts)
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def _wait_for(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    app.processEvents()
    assert predicate()


def _summary_for_detail(seconds=60, *, start="2026-10-20", end="2026-10-26"):
    return {
        "today": end, "range_start": start, "range_end": end,
        "categories": [{"category_key": "work", "category_name": "工作学习", "effective_seconds": seconds}],
        "total_effective_seconds": seconds, "total_label": "范围总计",
    }


def test_detail_load_does_not_block_gui_and_ignores_range_change(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    started = threading.Event()
    release = threading.Event()
    worker_thread = []

    def load_detail(*_args):
        worker_thread.append(threading.get_ident())
        started.set()
        release.wait(timeout=2)
        return [{"process_name": "old.exe", "window_title": "Old", "effective_seconds": 60}]

    monkeypatch.setattr(category_stats_service, "load_category_range_detail", load_detail)
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary(_summary_for_detail())
    page._is_active = True
    main_thread = threading.get_ident()
    try:
        page._expand_card("work")
        assert started.wait(timeout=1)
        assert worker_thread != [main_thread]
        labels = [label.text() for label in page._cards["work"]._detail.findChildren(QLabel)]
        assert any("加载" in label for label in labels)
        page.period_combo.setCurrentIndex(page.period_combo.findData("today"))
        release.set()
        _wait_for(app, lambda: page._detail_refresh_controller._worker is None)
        assert page._cards == {}
    finally:
        release.set()
        page.shutdown()
        page.deleteLater()
        app.processEvents()


def test_changed_summary_refreshes_expanded_detail(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []

    def load_detail(_db, start, end, key, _limit):
        calls.append((start, end, key))
        seconds = 60 if len(calls) == 1 else 120
        return [{"process_name": "work.exe", "window_title": "Work", "effective_seconds": seconds}]

    monkeypatch.setattr(category_stats_service, "load_category_range_detail", load_detail)
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary(_summary_for_detail())
    page._is_active = True
    try:
        page._expand_card("work")
        _wait_for(app, lambda: len(calls) == 1 and page._detail_refresh_controller._worker is None)
        page._apply_summary(_summary_for_detail(120))
        _wait_for(app, lambda: len(calls) == 2 and page._detail_refresh_controller._worker is None)
        table = page._cards["work"]._detail.layout().itemAt(0).widget()
        assert isinstance(table, QTableWidget)
        assert table.item(0, 2).text() == fmt_seconds(120)
        assert calls == [("2026-10-20", "2026-10-26", "work")] * 2
    finally:
        page.shutdown()
        page.deleteLater()
        app.processEvents()


def test_preset_date_fields_follow_new_summary_day_at_midnight(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary(_summary_for_detail(start="2026-10-21", end="2026-10-27"))
    assert page.start_edit.date() == QDate(2026, 10, 21)
    assert page.end_edit.date() == QDate(2026, 10, 27)
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def test_reexpand_same_category_republishes_identical_detail(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []

    def load_detail(*_args):
        calls.append(1)
        return [{"process_name": "same.exe", "window_title": "Same", "effective_seconds": 60}]

    monkeypatch.setattr(category_stats_service, "load_category_range_detail", load_detail)
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary(_summary_for_detail())
    page._is_active = True
    try:
        page._expand_card("work")
        _wait_for(app, lambda: len(calls) == 1 and page._detail_refresh_controller._worker is None)
        page._collapse_card("work")
        page._expand_card("work")
        _wait_for(app, lambda: len(calls) == 2 and page._detail_refresh_controller._worker is None)
        detail = page._cards["work"]._detail.layout().itemAt(0).widget()
        assert isinstance(detail, QTableWidget)
        assert detail.item(0, 0).text() == "same.exe"
    finally:
        page.shutdown()
        page.deleteLater()
        app.processEvents()


def test_expanded_detail_refreshes_when_distribution_changes_but_total_does_not(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []

    def load_detail(*_args):
        calls.append(1)
        process = "first.exe" if len(calls) == 1 else "second.exe"
        return [{"process_name": process, "window_title": process, "effective_seconds": 60}]

    monkeypatch.setattr(category_stats_service, "load_category_range_detail", load_detail)
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary(_summary_for_detail())
    page._is_active = True
    try:
        page._expand_card("work")
        _wait_for(app, lambda: len(calls) == 1 and page._detail_refresh_controller._worker is None)
        assert page._detail_refresh_controller.timer.interval() == 30_000
        page._detail_refresh_controller.request_refresh()
        _wait_for(app, lambda: len(calls) == 2 and page._detail_refresh_controller._worker is None)
        detail = page._cards["work"]._detail.layout().itemAt(0).widget()
        assert isinstance(detail, QTableWidget)
        assert detail.item(0, 0).text() == "second.exe"
    finally:
        page.shutdown()
        page.deleteLater()
        app.processEvents()


def test_expanded_detail_recovers_when_retry_returns_same_rows(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    rows = [{"process_name": "same.exe", "window_title": "Same", "effective_seconds": 60}]

    def load_detail(*_args):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("temporary read failure")
        return rows

    monkeypatch.setattr(category_stats_service, "load_category_range_detail", load_detail)
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary(_summary_for_detail())
    page._is_active = True
    try:
        page._expand_card("work")
        _wait_for(app, lambda: len(calls) == 1 and page._detail_refresh_controller._worker is None)
        page._detail_refresh_controller.request_refresh()
        _wait_for(app, lambda: len(calls) == 2 and page._detail_refresh_controller._worker is None)
        error = page._cards["work"]._detail.layout().itemAt(0).widget()
        assert isinstance(error, QLabel) and "读取失败" in error.text()
        page._detail_refresh_controller.request_refresh()
        _wait_for(app, lambda: len(calls) == 3 and page._detail_refresh_controller._worker is None)
        detail = page._cards["work"]._detail.layout().itemAt(0).widget()
        assert isinstance(detail, QTableWidget)
        assert detail.item(0, 0).text() == "same.exe"
    finally:
        page.shutdown()
        page.deleteLater()
        app.processEvents()


def test_category_summary_clears_error_when_retry_returns_same_snapshot(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    summary = _summary_for_detail()

    def load_summary(*_args):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("temporary summary failure")
        return summary

    monkeypatch.setattr(category_stats_service, "load_category_summary", load_summary)
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    try:
        page.activate()
        _wait_for(app, lambda: len(calls) == 1 and page._refresh_controller._worker is None)
        page._refresh_controller.request_refresh()
        _wait_for(app, lambda: len(calls) == 2 and page._refresh_controller._worker is None)
        assert page.error_lbl.isHidden() is False
        page._refresh_controller.request_refresh()
        _wait_for(app, lambda: len(calls) == 3 and page._refresh_controller._worker is None)
        assert page.error_lbl.isHidden() is True
    finally:
        page.shutdown()
        page.deleteLater()
        app.processEvents()


def test_range_detail_keeps_selected_category_when_global_top_fifty_are_elsewhere(tmp_path):
    db_path = str(tmp_path / "usage.db")
    conn = database.init_db(db_path)

    def add_session(index, day, category_key, seconds):
        start = datetime.fromisoformat(f"{day} 09:00:00") + timedelta(minutes=2 * index)
        database.insert_session(conn, ActivitySession(
            session_id=f"session-{day}-{index}", start_time=start,
            end_time=start + timedelta(seconds=seconds), date=day,
            process_name=f"{category_key}-{index}.exe", exe_path="C:/app.exe",
            window_title=f"Title {index}", normalized_title=f"Title {index}",
            category_key=category_key, category_name=category_key,
            active_rule="interactive_required", duration_seconds=seconds,
            effective_seconds=seconds,
        ))

    for index in range(55):
        add_session(index, "2026-10-21", "video", 100)
    add_session(80, "2026-10-20", "coding", 90)
    add_session(81, "2026-10-22", "reading", 80)
    add_session(82, "2026-10-19", "coding", 200)
    database.insert_activity_log(conn, {
        "timestamp": "2026-10-20 23:00:00", "date": "2026-10-20",
        "process_name": "legacy.exe", "window_title": "Legacy work",
        "category_key": "office", "category_name": "办公",
        "active_rule": "interactive_required", "is_user_active": True,
        "is_effective": True, "idle_seconds": 0, "duration_seconds": 70,
    })
    database.close_db(conn)

    rows = category_stats_service.load_category_range_detail(
        db_path, "2026-10-20", "2026-10-22", "work", 5,
    )
    assert [(row["process_name"], row["effective_seconds"]) for row in rows] == [
        ("coding-80.exe", 90), ("reading-81.exe", 80), ("legacy.exe", 70),
    ]
    summary = category_stats_service.load_category_summary(db_path, "2026-10-20", "2026-10-23")
    assert summary["total_effective_seconds"] == 5740
    assert [(row["category_key"], row["effective_seconds"]) for row in summary["categories"]] == [
        ("entertainment", 5500), ("work", 240),
    ]
