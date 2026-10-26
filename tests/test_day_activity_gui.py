import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


DAYS = [f"2026-10-{day:02d}" for day in range(19, 26)]


def app():
    return QApplication.instance() or QApplication([])


def wait_for(application, predicate):
    deadline = time.monotonic() + 4
    while not predicate() and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(.005)
    assert predicate()


def model(day=DAYS[-1]):
    events = []
    for identity, minute, effective in (("long", 0, 300), ("short", 10, 299)):
        start = 9 * 3600 + minute * 60
        events.append({
            "id": identity, "start_time": f"{day} 09:{minute:02d}:00",
            "end_time": f"{day} 09:{minute+5:02d}:00", "start_second": start,
            "end_second": start + 300, "app": "浏览器", "process_name": "chrome.exe",
            "title": "学习资料 <不是HTML> " + "长中文标题" * 30,
            "category_key": "reading", "category_name": "工作学习",
            "effective_seconds": effective, "duration_seconds": 300,
            "engaged_seconds": effective, "passive_seconds": 0,
            "idle_seconds": 300 - effective, "legacy": False,
            "contains_idle": effective < 300, "is_long": effective >= 300,
            "source_session_ids": [identity],
        })
    return {"day": day, "status": "ready", "captured_at": f"{day}T12:00:00",
            "last_recorded_at": f"{day} 09:15:00", "warnings": [], "events": events,
            "totals": {"effective_seconds": 599, "engaged_seconds": 599,
                       "passive_seconds": 0, "idle_seconds": 1},
            "segments": [{"kind": "activity", "start_second": e["start_second"],
                          "end_second": e["end_second"], "event_id": e["id"]}
                         for e in events]}


def test_dialog_filters_details_without_changing_timeline_or_totals():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_args, **_kw: model())
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        assert dialog.events_model.rowCount() == 1
        assert len(dialog.timeline.model["events"]) == 2
        assert dialog.model["totals"]["effective_seconds"] == 599
        dialog.events_table.selectRow(0)
        assert dialog.timeline.selected_event_id == "long"
        dialog.show_all.setChecked(True)
        assert dialog.events_model.rowCount() == 2
        assert "全部" in dialog.events_heading.text()
        assert dialog.events_model.data(dialog.events_model.index(1, 2)).startswith("学习资料 <不是HTML>")
        assert "含空闲" in dialog.events_model.data(dialog.events_model.index(1, 5))
        assert dialog.timeline.tooltip_for_second(9 * 3600 + 601)
        assert dialog.day_picker.count() == 7
    finally:
        dialog.close()


def test_only_short_events_explain_filter_instead_of_looking_like_no_records():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    short = model()
    short["events"] = short["events"][1:]
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: short)
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        assert dialog.events_model.rowCount() == 0
        assert "显示全部事件" in dialog.filter_hint.text()
        assert not dialog.filter_hint.isHidden()
        dialog.show_all.setChecked(True)
        assert dialog.events_model.rowCount() == 1
        assert dialog.filter_hint.isHidden()
    finally:
        dialog.close()


def test_fast_date_switch_and_close_ignore_stale_background_results():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    started, release = threading.Event(), threading.Event()
    calls = []

    def loader(_db, day, **_kwargs):
        calls.append(day)
        if len(calls) == 1:
            started.set()
            release.wait(3)
        return model(day)

    dialog = DayActivityDialog("unused", DAYS[0], DAYS, loader=loader)
    try:
        assert started.wait(1)
        dialog.day_picker.setCurrentIndex(1)
        dialog.day_picker.setCurrentIndex(2)
        release.set()
        wait_for(application, lambda: dialog.model.get("day") == DAYS[2]
                 and dialog.model.get("status") == "ready")
        assert calls == [DAYS[0], DAYS[2]]
        before = dict(dialog.model)
        dialog.close()
        dialog._results.put((0, DAYS[0], model(DAYS[0])))
        dialog._poll()
        assert dialog.model == before
    finally:
        release.set()
        dialog.close()


def test_close_during_read_stops_delivery_without_waiting_for_worker():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def loader(_db, day, **_kwargs):
        started.set()
        release.wait(3)
        finished.set()
        return model(day)

    dialog = DayActivityDialog("unused", DAYS[0], DAYS, loader=loader)
    try:
        assert started.wait(1)
        before = dict(dialog.model)
        start = time.monotonic()
        dialog.close()
        assert time.monotonic() - start < .3
        release.set()
        assert finished.wait(1)
        application.processEvents()
        dialog._poll()
        assert dialog.model == before
        assert not dialog._timer.isActive()
    finally:
        release.set()
        dialog.close()


def test_dialog_failure_is_retryable_and_empty_does_not_claim_idle():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    count = []

    def loader(*_args, **_kwargs):
        count.append(1)
        if len(count) == 1:
            raise OSError("synthetic failure")
        return {**model(), "status": "empty", "events": [], "segments": []}

    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=loader)
    try:
        wait_for(application, lambda: dialog.model.get("status") == "unavailable")
        assert dialog.refresh_button.isEnabled()
        dialog.refresh_button.click()
        wait_for(application, lambda: dialog.model.get("status") == "empty")
        assert "暂无可展开" in dialog.status_label.text()
        assert "不代表全天空闲" in dialog.status_label.text()
    finally:
        dialog.close()


def test_seven_day_work_columns_emit_iso_dates_for_zero_and_missing_days():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from daylens.gui.widgets.dashboard_widgets import RhythmComparisonCard

    application = app()
    card = RhythmComparisonCard()
    card.resize(700, 280)
    seen = []
    card.day_activated.connect(seen.append)
    card.set_data({"7d": {"chart": {"kind": "bars", "dates": DAYS,
                                    "labels": [str(i) for i in range(7)],
                                    "values": [60, 0, None, 60, 60, 60, 60]}},
                   "30d": {"chart": {"kind": "bars", "dates": DAYS,
                                      "values": [60] * 7}}})
    card.set_mode("7d")
    card.show()
    application.processEvents()
    canvas = card.canvas
    for index in (1, 2):
        x = 38 + (canvas.width() - 48) * (index + .5) / 7
        QTest.mouseClick(canvas, Qt.LeftButton, pos=QPoint(int(x), canvas.height() - 8))
    assert seen == [DAYS[1], DAYS[2]]
    card.set_mode("30d")
    QTest.mouseClick(canvas, Qt.LeftButton, pos=QPoint(100, 20))
    assert seen == [DAYS[1], DAYS[2]]
    card.close()


def test_seven_day_entertainment_emits_same_dates_but_heatmap_does_not():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from daylens.gui.widgets.dashboard_widgets import EntertainmentHistoryCard

    application = app()
    card = EntertainmentHistoryCard()
    card.resize(700, 250)
    points = [{"date": day, "has_data": index != 2, "seconds": 0}
              for index, day in enumerate(DAYS)]
    card.set_data({"entertainment_history": {"week": {"points": points},
                                            "month": {"points": points}}})
    seen = []
    card.day_activated.connect(seen.append)
    card.show()
    application.processEvents()
    for index in (1, 2):
        x = 4 + (card.canvas.width() - 8) * (index + .5) / 7
        QTest.mouseClick(card.canvas, Qt.LeftButton,
                         pos=QPoint(int(x), card.canvas.height() - 7))
    assert seen == [DAYS[1], DAYS[2]]
    card.set_mode("30d")
    QTest.mouseClick(card.canvas, Qt.LeftButton, pos=QPoint(100, 20))
    assert seen == [DAYS[1], DAYS[2]]
    card.close()


def test_dialog_geometry_fits_small_and_large_screens():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: model())
    try:
        for width, height in ((1100, 620), (1500, 900)):
            dialog.resize(width, height)
            dialog.show()
            application.processEvents()
            assert dialog.timeline.width() <= dialog.width()
            assert dialog.events_table.geometry().bottom() < dialog.height()
            assert dialog.day_picker.geometry().right() <= dialog.width()
    finally:
        dialog.close()


def test_compact_scaled_window_keeps_two_complete_event_rows_visible():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: model())
    try:
        dialog.resize(767, 432)  # 1280x720 at 150%, with window margins.
        dialog.show()
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        application.processEvents()
        assert dialog.events_table.viewport().height() >= 2 * dialog.events_table.verticalHeader().defaultSectionSize()
        dialog.scroll.ensureWidgetVisible(dialog.events_table)
        application.processEvents()
        point = dialog.events_table.mapTo(dialog.scroll.viewport(), dialog.events_table.rect().topLeft())
        assert 0 <= point.y() < dialog.scroll.viewport().height()
        assert dialog.timeline.width() <= dialog.scroll.viewport().width()
    finally:
        dialog.close()


def test_dialog_returns_to_one_fixed_day_axis_without_zoom_controls():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    calls = []
    def loader(*_a, **_k):
        calls.append(1)
        return model()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=loader)
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        assert not hasattr(dialog, "viewport")
        assert not hasattr(dialog, "overview")
        assert not hasattr(dialog, "zoom_in_button")
        assert not hasattr(dialog, "zoom_out_button")
        assert not hasattr(dialog, "coverage_value")
        assert dialog.timeline.labelled_hours == tuple(range(0, 25, 2))
        assert not dialog.summary_label.isHidden()
        original_summary = dialog.summary_label.text()
        dialog.show_all.setChecked(True)
        assert dialog.events_model.rowCount() == 2
        assert "全天" in dialog.events_heading.text()
        assert dialog.summary_label.text() == original_summary
        assert len(dialog.timeline.model["events"]) == 2
        assert len(calls) == 1
    finally:
        dialog.close()


def test_clicking_short_block_reveals_row_and_reverse_highlight():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: model())
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        dialog.timeline.event_activated.emit("short")
        assert dialog.show_all.isChecked()
        assert dialog.events_table.currentIndex().row() == 1
        assert dialog.timeline.selected_event_id == "short"
        dialog.events_table.selectRow(0)
        assert dialog.timeline.selected_event_id == "long"
    finally:
        dialog.close()


def test_refresh_and_date_change_keep_full_day_events():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda _db, day, **_k: model(day))
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        dialog.show_all.setChecked(True)
        dialog.refresh_button.click()
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        assert dialog.events_model.rowCount() == 2
        dialog.day_picker.setCurrentIndex(0)
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        assert dialog.events_model.rowCount() == 2
        assert dialog.timeline.model["day"] == DAYS[0]
    finally:
        dialog.close()


def test_day_axis_has_no_short_event_aggregation_or_ratio_track():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    source = model()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: source)
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        assert not hasattr(dialog.timeline, "aggregate_activated")
        assert not hasattr(dialog.timeline, "viewport")
        assert "下轨" not in dialog.help_label.text()
        dialog.show_all.setChecked(True)
        assert dialog.events_model.rowCount() == 2
        assert len(source["events"]) == 2
        assert source["totals"]["effective_seconds"] == 599
    finally:
        dialog.close()


def test_data_coverage_not_inferred_from_ready_status_or_future():
    from daylens.gui.widgets.day_activity_dialog import coverage_label

    source = model()
    source["segments"] = [
        {"kind": "missing", "start_second": 0, "end_second": 32400},
        *source["segments"],
        {"kind": "future", "start_second": 43200, "end_second": 86400},
    ]
    assert coverage_label(source) == "部分覆盖"
    source["segments"] = [{"kind": "activity", "start_second": 0, "end_second": 43200},
                          {"kind": "future", "start_second": 43200, "end_second": 86400}]
    assert coverage_label(source) == "截至当前"
    source["segments"] = [{"kind": "activity", "start_second": 0, "end_second": 86400}]
    assert coverage_label(source) == "完整覆盖"
    source["warnings"] = ["损坏记录"]
    assert coverage_label(source) == "含异常"


def test_full_day_threshold_and_tooltip_do_not_mention_removed_ratio_view():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: model())
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        assert dialog.events_model.rowCount() == 1
        assert dialog._visible_events[0]["effective_seconds"] == 300
        assert dialog.model["totals"]["effective_seconds"] == 599
        from PySide6.QtCore import Qt
        tooltip = dialog.events_model.data(dialog.events_model.index(0, 0), Qt.ToolTipRole)
        assert "前台范围" in tooltip
        assert "下轨" not in tooltip and "比例" not in tooltip
    finally:
        dialog.close()


def test_valid_legacy_and_display_name_notes_are_not_timing_anomalies():
    from daylens.gui.widgets.day_activity_dialog import coverage_label

    source = model()
    source["status"] = "partial"
    source["events"][0]["legacy"] = True
    source["segments"] = [{"kind": "activity", "start_second": 0, "end_second": 86400}]
    source["warnings"] = ["包含旧版计时记录；有效时长保留，主动与被动时长不可确定。",
                          "部分应用显示名称解析失败，已显示进程名。"]
    assert coverage_label(source) == "完整覆盖"
    source["warnings"].append("存在时间戳无效的记录，无法确定其活动区间。")
    assert coverage_label(source) == "含异常"


def test_dense_full_day_filter_stays_responsive_with_all_original_events():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    source = model()
    base = source["events"][0]
    source["events"] = [{**base, "id": str(i), "title": f"Window {i % 2}",
                         "start_second": i * 2, "end_second": i * 2 + 2,
                         "duration_seconds": 2, "effective_seconds": 2,
                         "engaged_seconds": 2, "passive_seconds": 0, "idle_seconds": 0,
                         "contains_idle": False, "is_long": False} for i in range(20000)]
    source["segments"] = [{"kind": "activity", "start_second": e["start_second"],
                           "end_second": e["end_second"], "event_id": e["id"]}
                          for e in source["events"]]
    source["totals"]["effective_seconds"] = 40000
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: source)
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        dialog.show_all.setChecked(True)
        started = time.monotonic()
        for _ in range(10):
            dialog.show_all.setChecked(False)
            dialog.show_all.setChecked(True)
            application.processEvents()
        assert time.monotonic() - started < 1.5
        assert dialog.events_table.model().rowCount() == 20000
        assert len(dialog.model["events"]) == 20000
        assert dialog.model["totals"]["effective_seconds"] == 40000
    finally:
        dialog.close()


def test_lazy_event_model_keeps_full_text_escaped_tooltips_and_readonly_flags():
    from PySide6.QtCore import QModelIndex, Qt
    from daylens.gui.widgets.day_activity_event_model import DayActivityEventModel

    application = app()
    table_model = DayActivityEventModel()
    source = model()["events"]
    table_model.set_events(source)
    index = table_model.index(0, 2)
    assert table_model.data(index) == source[0]["title"]
    assert "&lt;不是HTML&gt;" in table_model.data(index, Qt.ToolTipRole)
    assert not table_model.flags(index) & Qt.ItemIsEditable
    assert table_model.data(index, Qt.UserRole) == "long"
    assert table_model.row_for_id("short") == 1
    assert table_model.headerData(4, Qt.Horizontal) == "有效活动"
    assert table_model.rowCount(index) == 0
    assert table_model.data(QModelIndex()) is None
    source[0] = {**source[0], "legacy": True, "engaged_seconds": None,
                 "passive_seconds": None, "idle_seconds": None}
    table_model.set_events(source)
    tooltip = table_model.data(table_model.index(0, 0), Qt.ToolTipRole)
    assert "主动／被动分项未知" in tooltip
    assert "空闲 未知" in tooltip
    table_model.set_events([])
    assert table_model.rowCount() == 0
    assert table_model.row_for_id("long") is None
