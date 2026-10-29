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


def test_idle_labeled_session_reports_only_its_effective_part_as_other(tmp_path):
    db_path = tmp_path / "usage.db"
    conn = database.init_db(str(db_path))
    start = datetime(2026, 10, 27, 9, 0, 0)
    database.insert_session(
        conn,
        ActivitySession(
            session_id="idle-with-effective-evidence",
            start_time=start,
            end_time=start + timedelta(seconds=100),
            date="2026-10-27",
            process_name="explorer.exe",
            exe_path="C:/Windows/explorer.exe",
            window_title="Program Manager",
            normalized_title="Program Manager",
            category_key="idle",
            category_name="空闲",
            active_rule="interactive_required",
            duration_seconds=100,
            effective_seconds=60,
            engaged_seconds=60,
            passive_seconds=0,
            idle_seconds=40,
            metric_version="attention-v1",
            classification_version="rules-test",
        ),
    )
    database.close_db(conn)

    result = database.query_date_range_stats(str(db_path), ["2026-10-27"])
    categories = {row["category_key"]: row for row in result["by_category"]}

    assert result["totals"]["effective_seconds"] == 60
    assert categories["other"]["effective_seconds"] == 60
    assert categories["other"]["idle_seconds"] == 0
    assert categories["other"]["total_seconds"] == 60
    assert "idle" not in categories
    assert result["by_app"][0]["category_key"] == "other"


def test_legacy_idle_labeled_effective_sample_is_also_reported_as_other(tmp_path):
    db_path = tmp_path / "usage.db"
    conn = database.init_db(str(db_path))
    conn.execute(
        """
        INSERT INTO activity_logs
            (timestamp, date, process_name, window_title, category_key,
             category_name, is_effective, idle_seconds, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-10-27 09:00:00",
            "2026-10-27",
            "explorer.exe",
            "Program Manager",
            "idle",
            "空闲",
            1,
            0,
            30,
        ),
    )
    conn.commit()
    database.close_db(conn)

    result = database.query_date_range_stats(str(db_path), ["2026-10-27"])
    categories = {row["category_key"]: row for row in result["by_category"]}

    assert result["totals"]["effective_seconds"] == 30
    assert categories["other"]["effective_seconds"] == 30
    assert "idle" not in categories
    assert result["by_app"][0]["category_key"] == "other"


def test_statistics_opens_live_monitor_by_default_and_keeps_explicit_tabs():
    app = QApplication.instance() or QApplication([])
    software, category, goals, live = QWidget(), QWidget(), QWidget(), QWidget()
    page = StatisticsPage(software, category, goals, live_page=live)
    assert [page.tabs.tabText(index) for index in range(page.tabs.count())] == [
        "实时监控", "导出数据", "数据统计", "设置目标",
    ]
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


def test_range_summary_contains_bounded_normalized_category_details(monkeypatch):
    rows = [
        {
            "process_name": f"game{index}.exe",
            "window_title": f"Game {index}",
            "category_key": "gaming",
            "category_name": "游戏娱乐",
            "effective_seconds": 100 - index,
        }
        for index in range(6)
    ]
    rows.append({
        "process_name": "video.exe",
        "window_title": "Video",
        "category_key": "video",
        "category_name": "视频娱乐",
        "effective_seconds": 99,
    })
    monkeypatch.setattr(
        category_stats_service.database,
        "query_date_range_stats",
        lambda *_args: {
            "by_category": [
                {
                    "category_key": "gaming",
                    "category_name": "游戏娱乐",
                    "effective_seconds": 500,
                },
                {
                    "category_key": "video",
                    "category_name": "视频娱乐",
                    "effective_seconds": 99,
                },
            ],
            "category_details": {"gaming": rows[:6], "video": rows[6:]},
        },
    )

    result = category_stats_service.load_category_summary(
        "usage.db", "2026-10-20", "2026-10-22",
    )

    details = result["category_details"]["entertainment"]
    assert len(details) == 5
    assert [row["process_name"] for row in details] == [
        "game0.exe", "game1.exe", "video.exe", "game2.exe", "game3.exe",
    ]


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


def test_range_toolbar_shows_full_preset_summary_and_hides_custom_editors(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page.show()
    app.processEvents()

    expected = (
        f"{page.start_edit.date().toString('yyyy-MM-dd')} 至 "
        f"{page.end_edit.date().toString('yyyy-MM-dd')} · 共 7 天"
    )
    assert page.period_combo.minimumWidth() >= 140
    assert page.range_summary.text() == expected
    assert not page.custom_range_widget.isVisible()

    page.close()
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def test_custom_range_uses_wide_editors_and_calendar(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page.show()
    page.period_combo.setCurrentIndex(page.period_combo.findData("custom"))
    app.processEvents()

    assert page.custom_range_widget.isVisible()
    assert page.start_edit.minimumWidth() >= 150
    assert page.end_edit.minimumWidth() >= 150
    assert page.start_edit.calendarWidget().minimumWidth() >= 340
    assert page.start_edit.calendarWidget().minimumHeight() >= 260

    page.close()
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


def test_category_page_uses_selected_range_and_clicks_without_detail_query(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    seen = []
    monkeypatch.setattr(category_stats_service, "load_category_summary", lambda db, start, end: seen.append(("summary", start, end)) or {
        "today": end, "range_start": start, "range_end": end,
        "categories": [{"category_key": "work", "category_name": "工作学习", "effective_seconds": 60}],
        "category_details": {"work": [
            {"process_name": "work.exe", "window_title": "Work", "effective_seconds": 60},
        ]},
        "total_effective_seconds": 60, "total_label": "range total",
    })
    monkeypatch.setattr(
        category_stats_service,
        "load_category_range_detail",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected detail query")),
    )
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page.period_combo.setCurrentIndex(page.period_combo.findData("custom"))
    page.start_edit.setDate(QDate(2026, 10, 20))
    page.end_edit.setDate(QDate(2026, 10, 22))
    page._is_active = True
    page.refresh()
    page._expand_card("work")
    page._collapse_card("work")
    page._expand_card("work")
    assert seen == [("summary", "2026-10-20", "2026-10-22")]
    table = page._cards["work"]._detail.layout().itemAt(0).widget()
    assert isinstance(table, QTableWidget)
    assert table.item(0, 0).text() == "work.exe"
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
        "category_details": {"work": [
            {"process_name": "work.exe", "window_title": "Work", "effective_seconds": seconds},
        ]},
        "total_effective_seconds": seconds, "total_label": "范围总计",
    }


def test_summary_failure_keeps_expanded_snapshot(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary(_summary_for_detail())
    page._expand_card("work")
    table = page._cards["work"]._detail.layout().itemAt(0).widget()
    assert isinstance(table, QTableWidget)

    page._show_refresh_error("synthetic read failure")

    assert page.error_lbl.isHidden() is False
    assert page._cards["work"]._detail.layout().itemAt(0).widget() is table
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def test_changed_summary_refreshes_expanded_detail(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary(_summary_for_detail())
    page._expand_card("work")

    page._apply_summary(_summary_for_detail(120))

    table = page._cards["work"]._detail.layout().itemAt(0).widget()
    assert isinstance(table, QTableWidget)
    assert table.item(0, 2).text() == fmt_seconds(120)
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


def test_reexpand_same_category_uses_the_same_snapshot(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        category_stats_service,
        "load_category_range_detail",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected detail query")),
    )
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._apply_summary(_summary_for_detail())

    page._expand_card("work")
    page._collapse_card("work")
    page._expand_card("work")

    detail = page._cards["work"]._detail.layout().itemAt(0).widget()
    assert isinstance(detail, QTableWidget)
    assert detail.item(0, 0).text() == "work.exe"
    page.shutdown()
    page.deleteLater()
    app.processEvents()


def test_detail_only_summary_change_refreshes_expanded_card(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    first = _summary_for_detail()
    page._apply_summary(first)
    page._expand_card("work")
    changed = _summary_for_detail()
    changed["category_details"]["work"][0]["process_name"] = "second.exe"

    page._apply_summary(changed)

    detail = page._cards["work"]._detail.layout().itemAt(0).widget()
    assert isinstance(detail, QTableWidget)
    assert detail.item(0, 0).text() == "second.exe"
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
