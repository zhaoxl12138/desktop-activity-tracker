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


def mixed_category_model(day=DAYS[-1]):
    source = model(day)
    entertainment = dict(source["events"][0])
    entertainment.update(
        id="video-long", start_second=10 * 3600, end_second=10 * 3600 + 420,
        app="腾讯视频", process_name="QQLive.exe", title="完整的娱乐节目标题" * 12,
        category_key="video", category_name="视频娱乐",
        effective_seconds=420, engaged_seconds=0, passive_seconds=420,
        duration_seconds=420, idle_seconds=0, source_session_ids=["video-long"],
    )
    short = dict(entertainment)
    short.update(
        id="video-short", start_second=11 * 3600, end_second=11 * 3600 + 120,
        effective_seconds=120, passive_seconds=120, duration_seconds=120,
        source_session_ids=["video-short"],
    )
    source["events"].extend([entertainment, short])
    source["segments"].extend(
        {"kind": "activity", "start_second": item["start_second"],
         "end_second": item["end_second"], "event_id": item["id"]}
        for item in (entertainment, short)
    )
    source["totals"]["effective_seconds"] = 1139
    return source


def test_event_table_uses_balanced_columns_at_compact_and_wide_sizes():
    from PySide6.QtCore import Qt
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS,
                               loader=lambda *_a, **_k: mixed_category_model())
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        for width in (780, 1150, 1600):
            dialog.resize(width, 700)
            dialog.show()
            application.processEvents()
            dialog.scroll.ensureWidgetVisible(dialog.events_table)
            application.processEvents()
            viewport = dialog.events_table.viewport().width()
            columns = [dialog.events_table.columnWidth(i) for i in range(6)]
            assert sum(columns) <= viewport + 2
            assert columns[2] <= max(220, int(viewport * .40))
            assert columns[0] >= 110 and columns[3] >= 90
            assert columns[4] >= 95 and columns[5] >= 75
        tooltip = dialog.events_model.data(dialog.events_model.index(0, 2), Qt.ToolTipRole)
        assert "学习资料 &lt;不是HTML&gt;" in tooltip
        assert "长中文标题" * 30 in tooltip
    finally:
        dialog.close()


def test_category_filter_intersects_duration_toggle_without_changing_totals():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    source = mixed_category_model()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: source)
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        original_summary = dialog.summary_label.text()
        assert dialog.events_model.rowCount() == 2
        dialog.category_buttons["entertainment"].click()
        assert dialog.selected_category == "entertainment"
        assert dialog.category_buttons["entertainment"].isChecked()
        assert "QPushButton:checked" in dialog.category_buttons["entertainment"].styleSheet()
        assert [lane["key"] for lane in dialog.timeline.lanes] == ["entertainment"]
        assert dialog.events_model.rowCount() == 1
        assert dialog.events_model.data(dialog.events_model.index(0, 1)) == "腾讯视频"
        dialog.show_all.setChecked(True)
        assert dialog.events_model.rowCount() == 2
        assert dialog.summary_label.text() == original_summary
        assert dialog.model["totals"]["effective_seconds"] == 1139
        assert len(source["events"]) == 4
        dialog.category_buttons["all"].click()
        assert dialog.selected_category is None
        assert dialog.events_model.rowCount() == 4
        assert len(dialog.timeline.lanes) == 2
    finally:
        dialog.close()


def test_timeline_category_label_filters_and_date_change_resets_to_all():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS,
                               loader=lambda _db, day, **_k: mixed_category_model(day))
    try:
        dialog.show()
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        dialog.show_all.setChecked(True)
        video_row = dialog.events_model.row_for_id("video-long")
        dialog.events_table.selectRow(video_row)
        assert dialog.timeline.selected_event_id == "video-long"
        lane_index = next(i for i, lane in enumerate(dialog.timeline.lanes)
                          if lane["key"] == "work")
        point = QPoint(25, int(dialog.timeline._band(lane_index).center().y()))
        QTest.mouseClick(dialog.timeline, Qt.LeftButton, pos=point)
        assert dialog.selected_category == "work"
        assert dialog.timeline.selected_event_id is None
        assert dialog.events_model.row_for_id("video-long") is None
        dialog.day_picker.setCurrentIndex(0)
        wait_for(application, lambda: dialog.model.get("day") == DAYS[0]
                 and dialog.model.get("status") == "ready")
        assert dialog.selected_category is None
        assert dialog.category_buttons["all"].isChecked()
        assert len(dialog.timeline.lanes) == 2
        assert dialog.events_model.rowCount() == 4
    finally:
        dialog.close()


def test_filtered_category_keeps_idle_context_but_does_not_select_idle_row():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    source = mixed_category_model()
    idle = dict(source["events"][0])
    idle.update(id="known-idle", start_second=10 * 3600 + 1800,
                end_second=10 * 3600 + 1860, app="桌面", title="空闲",
                category_key="idle", category_name="空闲", effective_seconds=0,
                engaged_seconds=0, passive_seconds=0, idle_seconds=60,
                duration_seconds=60, source_session_ids=["known-idle"])
    source["events"].append(idle)
    source["segments"].append({"kind": "idle", "start_second": idle["start_second"],
                               "end_second": idle["end_second"], "event_id": idle["id"]})
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: source)
    try:
        dialog.show()
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        dialog.category_buttons["entertainment"].click()
        assert (dialog.timeline.range_start, dialog.timeline.range_end) == (9 * 3600, 11 * 3600 + 1800)
        band = dialog.timeline._band(0)
        x = dialog.timeline._x(10 * 3600 + 1830)
        QTest.mouseClick(dialog.timeline, Qt.LeftButton, pos=QPoint(int(x), int(band.center().y())))
        assert dialog.timeline.selected_event_id is None
        assert dialog.events_model.row_for_id("known-idle") is None
    finally:
        dialog.close()


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


def test_hidden_idle_event_stays_in_details_and_explains_missing_plot_block():
    from daylens.gui.widgets.day_activity_dialog import DayActivityDialog

    application = app()
    source = model()
    hidden = dict(source["events"][0])
    hidden.update(id="hidden-idle", start_second=12*3600, end_second=12*3600+1100,
                  start_time=f"{DAYS[-1]} 12:00:00", end_time=f"{DAYS[-1]} 12:18:20",
                  duration_seconds=1100, effective_seconds=300, engaged_seconds=300,
                  idle_seconds=800, contains_idle=True, source_session_ids=["hidden-idle"])
    source["events"].append(hidden)
    source["segments"].append({"kind": "activity", "start_second": hidden["start_second"],
                               "end_second": hidden["end_second"], "event_id": hidden["id"]})
    source["totals"]["effective_seconds"] += 300
    dialog = DayActivityDialog("unused", DAYS[-1], DAYS, loader=lambda *_a, **_k: source)
    try:
        wait_for(application, lambda: dialog.model.get("status") == "ready")
        assert dialog.events_model.rowCount() == 2
        assert "14分59秒" in dialog.summary_label.text()
        assert dialog.timeline.event_rect("hidden-idle").isEmpty()
        dialog.events_table.selectRow(dialog.events_model.row_for_id("hidden-idle"))
        assert "空闲占比超过70%" in dialog.help_label.text()
        assert dialog.model["totals"]["effective_seconds"] == 899
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
        x = canvas._bar_slot(index, canvas._chart_rect()).center().x()
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


def test_dialog_has_one_fitted_day_axis_without_zoom_controls():
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
        assert (dialog.timeline.range_start, dialog.timeline.range_end) == (32400, 34200)
        assert not dialog.summary_label.isHidden()
        original_summary = dialog.summary_label.text()
        original_range = (dialog.timeline.range_start, dialog.timeline.range_end)
        dialog.show_all.setChecked(True)
        assert dialog.events_model.rowCount() == 2
        assert "全天" in dialog.events_heading.text()
        assert dialog.summary_label.text() == original_summary
        assert (dialog.timeline.range_start, dialog.timeline.range_end) == original_range
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
