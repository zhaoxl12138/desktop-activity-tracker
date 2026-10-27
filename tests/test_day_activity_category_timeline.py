"""Activity-fitted category lanes preserve the original full-day evidence."""
import copy
import importlib.util
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QFontMetricsF, QMouseEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QToolTip


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


def event(identity="one", start=3600, end=7200, category="reading", **changes):
    result = dict(id=identity, start_second=start, end_second=end,
                  app="阅读器", title="资料 <b>不是标记</b>", category_key=category,
                  duration_seconds=1000, effective_seconds=800, engaged_seconds=500,
                  passive_seconds=300, idle_seconds=200, legacy=False, contains_idle=True)
    result.update(changes)
    return result


def model(events, segments=None):
    return dict(events=events, segments=segments if segments is not None else [
        dict(kind="idle" if e["category_key"] == "idle" else "activity",
             start_second=e["start_second"], end_second=e["end_second"], event_id=e["id"])
        for e in events])


def canvas(application, source=None, width=800):
    from daylens.gui.widgets.day_activity_category_timeline import DayActivityCategoryTimeline
    widget = DayActivityCategoryTimeline()
    widget.set_model(source if source is not None else model([event()]))
    widget.resize(width, widget.minimumHeight())
    widget.show()
    application.processEvents()
    return widget


def test_fixed_category_component_exists():
    assert importlib.util.find_spec("daylens.gui.widgets.day_activity_category_timeline") is not None


def test_axis_fits_first_and_last_activity_with_half_hour_rounding(application):
    source = model([event("morning", 9*3600+42*60, 10*3600),
                    event("noon", 12*3600, 12*3600+40*60, "video")])
    widget = canvas(application, source, width=620)
    try:
        band = widget._band()
        assert (widget.range_start, widget.range_end) == (9*3600+30*60, 13*3600)
        assert widget._x(widget.range_start) == band.left()
        assert widget._x(widget.range_end) == band.right()
        assert widget._second(band.center().x()) == pytest.approx((widget.range_start+widget.range_end)/2)
        assert not hasattr(widget, "viewport")
        labels = widget.hour_labels()
        assert labels[0][2] == "09:30" and labels[-1][2] == "13:00"
        for (_, left, _), (_, right, _) in zip(labels, labels[1:]):
            assert left.right() <= right.left()
        assert all(0 <= rect.left() < rect.right() <= widget.width() for _, rect, _ in labels)
    finally:
        widget.close()


@pytest.mark.parametrize("idle, hidden", [(69, False), (70, False), (71, True)])
def test_high_idle_visibility_uses_strict_seventy_percent_boundary(application, idle, hidden):
    source = model([event("mixed", 9*3600, 10*3600,
                          duration_seconds=100, idle_seconds=idle,
                          effective_seconds=100-idle)])
    widget = canvas(application, source)
    try:
        assert widget.is_event_hidden("mixed") is hidden
        assert widget.event_rect("mixed").isEmpty() is hidden
        if hidden:
            assert (widget.range_start, widget.range_end) == (0, 86400)
            assert "暂无可展示" in widget.range_title()
        else:
            assert (widget.range_start, widget.range_end) == (9*3600, 10*3600)
    finally:
        widget.close()


def test_high_idle_event_does_not_stretch_axis_or_accept_plot_click(application):
    from PySide6.QtCore import QPoint

    source = model([event("visible", 9*3600, 10*3600,
                          duration_seconds=100, idle_seconds=0, effective_seconds=100),
                    event("hidden", 14*3600, 21*3600, "tools",
                          duration_seconds=25174, idle_seconds=25173, effective_seconds=1)])
    widget = canvas(application, source)
    try:
        assert (widget.range_start, widget.range_end) == (9*3600, 10*3600)
        assert widget.event_rect("hidden").isEmpty()
        assert widget.lanes[-1]["effective_seconds"] == 1
        spy = QSignalSpy(widget.event_activated)
        band = widget._band(widget._lane_indices["tools"])
        QTest.mouseClick(widget, Qt.LeftButton,
                         pos=QPoint(round(band.center().x()), round(band.center().y())))
        assert spy.count() == 0
    finally:
        widget.close()


def test_hidden_event_inside_visible_range_has_no_hit_target(application):
    from PySide6.QtCore import QPoint

    source = model([event("morning", 9*3600, 10*3600,
                          duration_seconds=100, idle_seconds=0),
                    event("hidden", 12*3600, 13*3600, "tools",
                          duration_seconds=100, idle_seconds=71, effective_seconds=29),
                    event("evening", 15*3600, 16*3600, "video",
                          duration_seconds=100, idle_seconds=0)])
    widget = canvas(application, source)
    try:
        assert (widget.range_start, widget.range_end) == (9*3600, 16*3600)
        assert "空闲占比超过70%" in widget.tooltip_for_second(12*3600+30, "tools")
        spy = QSignalSpy(widget.event_activated)
        band = widget._band(widget._lane_indices["tools"])
        picture = widget.grab().toImage()
        row = round(band.center().y())
        assert picture.pixelColor(round(widget._x(12*3600+17*60)), row) == picture.pixelColor(
            round(widget._x(11*3600+17*60)), row)
        QTest.mouseClick(widget, Qt.LeftButton,
                         pos=QPoint(round(widget._x(12*3600+30)), round(band.center().y())))
        assert spy.count() == 0
    finally:
        widget.close()


def test_groups_share_work_lane_without_mutating_source_categories(application):
    categories = ["coding", "reading", "office", "ai_tools", "creative", "gaming",
                  "video", "social", "finance", "browser_general", "tools", "custom-label"]
    source = model([event(str(i), i*3600, (i+1)*3600, key) for i, key in enumerate(categories)])
    before = copy.deepcopy(source)
    widget = canvas(application, source)
    try:
        assert [(lane["key"], lane["name"]) for lane in widget.lanes] == [
            ("work", "工作学习"), ("entertainment", "娱乐休闲"), ("social", "社交通讯"),
            ("finance", "投资理财"), ("browser_general", "浏览器"), ("tools", "系统工具"), ("other", "其他")]
        assert all(widget.event_rect(str(i)).top() == widget.event_rect("0").top() for i in range(5))
        assert widget.model is source and source == before
        assert widget.minimumHeight() <= 390
        assert not widget.grab().isNull()
    finally:
        widget.close()


def test_empty_and_idle_only_days_keep_primary_orientation_lanes(application):
    widget = canvas(application, model([]))
    try:
        assert [lane["key"] for lane in widget.lanes] == ["work", "entertainment", "social", "finance"]
        source = model([event("idle", 0, 100, "idle", effective_seconds=0,
                                    engaged_seconds=0, passive_seconds=0, idle_seconds=100)])
        widget.set_model(source)
        assert "idle" not in [lane["key"] for lane in widget.lanes]
        widget.select_event("idle")
        assert widget.selected_event_id == "idle"
        assert widget.event_rect("idle").isEmpty()
        assert "空闲" in widget.tooltip_for_second(50)
    finally:
        widget.close()


@pytest.mark.parametrize("alias", ["idle_leave", "hangup"])
def test_idle_category_aliases_keep_neutral_idle_background(application, alias):
    canonical = canvas(application, model([event("idle", 10000, 20000, "idle")]))
    legacy_alias = canvas(application, model([event("idle", 10000, 20000, alias)]))
    try:
        area = canonical._column(11000, 19000).toRect()
        assert canonical.grab(area).toImage() == legacy_alias.grab(area).toImage()
    finally:
        canonical.close()
        legacy_alias.close()


def test_event_geometry_never_expands_short_sources_or_bridges_gaps(application):
    widget = canvas(application, model([event("left", 0, 1), event("right", 3, 4)]))
    try:
        left, right = widget.event_rect("left"), widget.event_rect("right")
        assert left.width() == pytest.approx(widget._band().width()/(widget.range_end-widget.range_start))
        assert left.right() < right.left()
        assert "无记录" in widget.tooltip_for_second(2, "work")
        assert widget.event_rect("absent").isNull()
    finally:
        widget.close()


@pytest.mark.parametrize("start,end,expected", [
    (0, 1, (0, 1800)),
    (36000, 36001, (36000, 37800)),
    (86399, 86400, (84600, 86400)),
    (0, 86400, (0, 86400)),
])
def test_activity_range_midnight_single_event_and_full_day(application, start, end, expected):
    widget = canvas(application, model([event(start=start, end=end)]))
    try:
        assert (widget.range_start, widget.range_end) == expected
        assert widget.event_rect("one").width() > 0
        assert widget.hour_labels()[0][2] == f"{expected[0]//3600:02d}:{expected[0]%3600//60:02d}"
        assert widget.hour_labels()[-1][2] == f"{expected[1]//3600:02d}:{expected[1]%3600//60:02d}"
    finally:
        widget.close()


def test_leading_and_trailing_idle_do_not_determine_active_range(application):
    source = model([
        event("idle_before", 0, 9*3600, "idle", effective_seconds=0),
        event("active", 9*3600+42*60, 12*3600+40*60),
        event("zero", 15*3600, 16*3600, effective_seconds=0),
        event("idle_after", 16*3600, 86400, "idle", effective_seconds=0),
    ])
    before = copy.deepcopy(source)
    widget = canvas(application, source)
    try:
        assert (widget.range_start, widget.range_end) == (34200, 46800)
        assert widget.event_rect("idle_before").isEmpty()
        assert widget.event_rect("idle_after").isEmpty()
        assert widget.event_rect("zero").isEmpty()
        assert len(widget.model["events"]) == 4 and source == before
    finally:
        widget.close()


def test_internal_idle_and_missing_intervals_keep_real_proportions(application):
    source = model([event("left", 9*3600, 10*3600), event("right", 12*3600, 13*3600)], [
        dict(kind="activity", start_second=32400, end_second=36000, event_id="left"),
        dict(kind="idle", start_second=36000, end_second=39600),
        dict(kind="missing", start_second=39600, end_second=43200),
        dict(kind="activity", start_second=43200, end_second=46800, event_id="right"),
    ])
    before = copy.deepcopy(source)
    widget = canvas(application, source)
    try:
        assert (widget.range_start, widget.range_end) == (32400, 46800)
        assert widget._x(43200)-widget._x(36000) == pytest.approx(widget._band().width()/2)
        assert "空闲" in widget.tooltip_for_second(38000)
        assert "无记录" in widget.tooltip_for_second(41000)
        assert source == before
    finally:
        widget.close()


@pytest.mark.parametrize("span", [(0, 86400), (34200, 46800), (36000, 37800), (1800, 84600)])
def test_adaptive_clock_labels_never_overlap_at_narrow_and_wide_widths(application, span):
    source = model([event(start=span[0], end=span[1])])
    widget = canvas(application, source)
    try:
        for width in (420, 620, 1180):
            widget.resize(width, widget.minimumHeight())
            labels = widget.hour_labels()
            assert labels[0][0] == span[0] and labels[-1][0] == span[1]
            for (_, left, _), (_, right, _) in zip(labels, labels[1:]):
                assert left.right()+2 <= right.left()
            assert all(rect.left() >= 0 and rect.right() <= width for _, rect, _ in labels)
    finally:
        widget.close()


def test_no_effective_activity_keeps_day_reference_and_empty_range_state(application):
    for source in (model([]), model([event("idle", 10000, 50000, "idle", effective_seconds=0)])):
        widget = canvas(application, source)
        try:
            assert (widget.range_start, widget.range_end) == (0, 86400)
            assert not widget.has_activity_range
            assert "暂无可展示活动" in widget.range_title()
        finally:
            widget.close()


def test_fractional_foreground_end_rounds_outward_and_keeps_mixed_idle_unknown(application):
    source = model([event("mixed", 34200.5, 45000.25, idle_seconds=200, contains_idle=True)])
    widget = canvas(application, source)
    try:
        assert (widget.range_start, widget.range_end) == (34200, 46800)
        assert "含空闲" in widget.tooltip_for_second(40000)
        assert "09:30–13:00" in widget.range_title()
        assert widget.model["events"][0]["end_second"] == 45000.25
    finally:
        widget.close()


def test_plot_right_boundary_does_not_select_trimmed_idle_after_activity(application):
    from PySide6.QtCore import QPoint

    source = model([event("active", 32400, 34200),
                    event("idle_after", 34200, 86400, "idle", effective_seconds=0)])
    widget = canvas(application, source)
    try:
        spy = QSignalSpy(widget.event_activated)
        band = widget._band()
        QTest.mouseClick(widget, Qt.LeftButton, pos=QPoint(round(band.right()), round(band.center().y())))
        assert spy.count() == 1 and spy.at(0) == ["active"]
        assert widget.event_rect("idle_after").isEmpty()
    finally:
        widget.close()


def test_click_and_selection_keep_original_ids_and_group_hit_testing(application):
    source = model([event("original", 3600, 7200), event("video", 7200, 10800, "video")])
    widget = canvas(application, source)
    try:
        spy = QSignalSpy(widget.event_activated)
        center = widget.event_rect("original").center().toPoint()
        QTest.mouseClick(widget, Qt.LeftButton, pos=center)
        assert spy.count() == 1 and spy.at(0) == ["original"]
        assert widget.selected_event_id == "original"
        widget.select_event("video")
        assert widget.selected_event_id == "video"
        assert "阅读器" not in widget.tooltip_for_second(5000, "entertainment")
        assert widget.model is source
    finally:
        widget.close()


def test_plain_tooltip_preserves_counters_and_unknown_idle_position(application):
    widget = canvas(application)
    try:
        text = widget.tooltip_for_second(4000, "work")
        for expected in ("资料 <b>不是标记</b>", "前台范围", "不代表全程有效", "主动参与",
                         "被动活动", "空闲", "含空闲", "位置"):
            assert expected in text
        assert "比例" not in text and "下轨" not in text
        widget.set_model(model([event(legacy=True, engaged_seconds=None, passive_seconds=None)]))
        assert "主动／被动分项未知" in widget.tooltip_for_second(4000)
    finally:
        widget.close()


def test_qtooltip_escapes_source_markup(application, monkeypatch):
    widget = canvas(application)
    shown = []
    # Reproduce a cursor already left at this exact point by a preceding test.
    QTest.mouseMove(widget, widget.event_rect("one").center().toPoint())
    application.processEvents()
    monkeypatch.setattr(QToolTip, "showText", lambda *args: shown.append(args[1]))
    try:
        local = widget.event_rect("one").center()
        global_position = widget.mapToGlobal(local.toPoint()).toPointF()
        move = QMouseEvent(QEvent.MouseMove, local, global_position,
                           Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        QApplication.sendEvent(widget, move)
        application.processEvents()
        assert shown and "&lt;b&gt;不是标记&lt;/b&gt;" in shown[-1]
        assert "<b>不是标记</b>" not in shown[-1]
    finally:
        widget.close()


@pytest.mark.parametrize("kind,text", [("missing", "无记录"), ("idle", "空闲"),
    ("future", "尚未"), ("unreliable", "异常")])
def test_neutral_states_have_distinct_paint_and_explanations(application, kind, text):
    source = model([], [dict(kind=kind, start_second=10000, end_second=20000)])
    widget = canvas(application, source)
    try:
        assert text in widget.tooltip_for_second(15000)
        assert not widget.grab().isNull()
        assert [lane["key"] for lane in widget.lanes] == ["work", "entertainment", "social", "finance"]
    finally:
        widget.close()


def test_labels_are_elided_only_inside_sufficient_original_event_width(application):
    source = model([event("short", 0, 1), event("long", 100, 40000,
                         app="极长的应用名称，不能越出前台记录色块"*5)])
    widget = canvas(application, source)
    try:
        metrics = QFontMetricsF(widget.font())
        assert widget._event_label(widget._events["short"], widget.event_rect("short"), metrics) == ""
        label = widget._event_label(widget._events["long"], widget.event_rect("long"), metrics)
        assert label and metrics.horizontalAdvance(label) <= widget.event_rect("long").width()-10
        assert "极长的应用名称" in widget.tooltip_for_second(30000)
    finally:
        widget.close()


def test_short_app_label_uses_actual_text_width_before_elision_threshold(application):
    widget = canvas(application)
    try:
        metrics = QFontMetricsF(widget.font())
        for app in ("WPS", "I"):
            source = event(app=app)
            rect = QRectF(0, 0, metrics.horizontalAdvance(app)+10, 28)
            assert widget._event_label(source, rect, metrics) == app
        source["app"] = "编辑器"
        available = metrics.horizontalAdvance("编…")
        rect.setWidth(available+10)
        label = widget._event_label(source, rect, metrics)
        assert label and metrics.horizontalAdvance(label) <= available
    finally:
        widget.close()


def test_dense_day_retains_every_id_and_counter_without_aggregation(application):
    events = [event(str(i), i*2, i*2+1, duration_seconds=1, effective_seconds=1,
                    engaged_seconds=1, passive_seconds=0, idle_seconds=0, contains_idle=False)
              for i in range(20000)]
    source = model(events)
    before = copy.deepcopy(source)
    started = time.monotonic()
    widget = canvas(application, source)
    try:
        assert len(widget._events) == len(events)
        assert set(widget._events) == {e["id"] for e in events}
        for _ in range(100):
            assert "前台范围" in widget.tooltip_for_second(39998)
        assert not widget.grab().isNull()
        assert time.monotonic()-started < 5
        assert source == before
        assert sum(e["effective_seconds"] for e in source["events"]) == 20000
    finally:
        widget.close()
