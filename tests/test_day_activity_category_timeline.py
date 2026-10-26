"""Fixed full-day category lanes preserve the original activity evidence."""
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


def test_fixed_axis_has_exact_full_day_endpoints_and_even_clock_labels(application):
    widget = canvas(application, width=620)
    try:
        band = widget._band()
        assert widget.tick_hours == tuple(range(25))
        assert widget.labelled_hours == tuple(range(0, 25, 2))
        assert widget._x(0) == band.left()
        assert widget._x(86400) == band.right()
        assert not hasattr(widget, "viewport")
        labels = widget.hour_labels()
        assert labels[0][2].startswith("00") and labels[-1][2].startswith("24")
        for (_, left, _), (_, right, _) in zip(labels, labels[1:]):
            assert left.right() <= right.left()
        assert all(0 <= rect.left() < rect.right() <= widget.width() for _, rect, _ in labels)
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
        assert widget.event_rect("idle").height() > widget._band().height()
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
        assert left.width() == pytest.approx(widget._band().width()/86400)
        assert left.right() < right.left()
        assert "无记录" in widget.tooltip_for_second(2, "work")
        assert widget.event_rect("absent").isNull()
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
