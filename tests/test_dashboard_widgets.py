from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker.gui.widgets.dashboard_widgets import TrendChartWidget, TimelineWidget, _TrendCanvas  # noqa: E402


def _app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_timeline_widget_expand_and_collapse():
    app = _app()
    widget = TimelineWidget(max_rows=2)
    sessions = [
        {
            "start_time": "2026-06-02 09:00:00",
            "end_time": "2026-06-02 09:25:00",
            "process_name": "Code.exe",
            "category_name": "工作学习",
            "category_key": "coding",
            "effective_seconds": 1500,
        },
        {
            "start_time": "2026-06-02 09:30:00",
            "end_time": "2026-06-02 09:45:00",
            "process_name": "WeChat.exe",
            "category_name": "社交通讯",
            "category_key": "social",
            "effective_seconds": 900,
        },
        {
            "start_time": "2026-06-02 10:00:00",
            "end_time": "2026-06-02 10:40:00",
            "process_name": "chrome.exe",
            "category_name": "娱乐休闲",
            "category_key": "video",
            "effective_seconds": 2400,
        },
    ]

    widget.set_sessions(sessions, {"Code.exe": "VS Code", "WeChat.exe": "微信"})
    widget.show()
    app.processEvents()

    assert len(widget._rows) == 3
    assert widget.more_label.text() == "收起 ↑"
    assert widget.more_label.isEnabled() is True

    widget.more_label.click()
    app.processEvents()

    assert len(widget._rows) == 2
    assert widget.more_label.text() == "查看更多 ↓"

    widget.more_label.click()
    app.processEvents()

    assert len(widget._rows) == 3
    assert widget.more_label.text() == "收起 ↑"


def test_timeline_widget_hides_expand_behavior_for_short_lists():
    app = _app()
    widget = TimelineWidget(max_rows=3)
    sessions = [
        {
            "start_time": "2026-06-02 09:00:00",
            "end_time": "2026-06-02 09:10:00",
            "process_name": "Code.exe",
            "category_name": "工作学习",
            "category_key": "coding",
            "effective_seconds": 600,
        }
    ]

    widget.set_sessions(sessions)
    widget.show()
    app.processEvents()

    assert len(widget._rows) == 1
    assert widget.more_label.isVisible() is False


def test_timeline_widget_can_open_detail_dialog():
    app = _app()
    widget = TimelineWidget(max_rows=2, show_title=False, open_detail_on_more=True)
    sessions = [
        {
            "start_time": "2026-06-02 09:00:00",
            "end_time": "2026-06-02 09:25:00",
            "process_name": "Code.exe",
            "category_name": "工作学习",
            "category_key": "coding",
            "effective_seconds": 1500,
        },
        {
            "start_time": "2026-06-02 09:30:00",
            "end_time": "2026-06-02 09:45:00",
            "process_name": "WeChat.exe",
            "category_name": "社交通讯",
            "category_key": "social",
            "effective_seconds": 900,
        },
        {
            "start_time": "2026-06-02 10:00:00",
            "end_time": "2026-06-02 10:40:00",
            "process_name": "chrome.exe",
            "category_name": "娱乐休闲",
            "category_key": "video",
            "effective_seconds": 2400,
        },
    ]

    widget.set_sessions(sessions)
    widget.show()
    app.processEvents()

    assert widget.more_label.text() == "查看全部 ↗"
    widget.more_label.click()
    app.processEvents()

    assert widget._detail_dialog is not None
    assert widget._detail_dialog.isVisible() is True


def test_trend_canvas_renders_sparse_weekly_series():
    canvas = _TrendCanvas()

    canvas.set_series([0, 0, 2.5, 0, 0, 0, 0], [""] * 7, "7d", [])
    assert canvas._series_state() == "chart"

    canvas.set_series([0, 0, 18, 0, 0, 0, 0], [""] * 7, "today", [])
    assert canvas._series_state() == "accumulating"


def test_trend_widget_middle_button_switches_to_week_mode():
    app = _app()
    widget = TrendChartWidget()
    widget.set_data(
        [0, 0, 18, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0] * 24,
        [0, 0, 2.5, 0, 0, 0, 0],
        [0, 0, 1.5] + [0] * 27,
    )
    widget.show()
    app.processEvents()

    widget._mode_buttons["7d"].click()
    app.processEvents()

    assert widget._mode == "7d"
    assert widget.canvas._mode == "7d"
    assert widget.canvas._series_state() == "chart"
    assert widget._mode_buttons["7d"].isChecked() is True
