from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker.gui.widgets.dashboard_widgets import (  # noqa: E402
    SessionTop3Widget,
    TimelineWidget,
    TrendChartWidget,
    _TrendCanvas,
)
from daylens.gui.widgets import dashboard_widgets  # noqa: E402


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

    assert widget.more_label.text() == "查看全部 Session (3) ↗"
    widget.more_label.click()
    app.processEvents()

    assert widget._detail_dialog is not None
    assert widget._detail_dialog.isVisible() is True


def test_timeline_widget_filters_short_sessions_into_focus_cards():
    app = _app()
    widget = TimelineWidget(max_rows=4, min_effective_seconds=600, sort_by_value=True)
    sessions = [
        {
            "start_time": "2026-06-02 09:00:00",
            "end_time": "2026-06-02 09:04:00",
            "process_name": "Code.exe",
            "window_title": "Code",
            "normalized_title": "Code",
            "category_name": "工作学习",
            "category_key": "coding",
            "effective_seconds": 240,
            "duration_seconds": 240,
        },
        {
            "start_time": "2026-06-02 10:00:00",
            "end_time": "2026-06-02 10:30:00",
            "process_name": "WeChat.exe",
            "window_title": "微信",
            "normalized_title": "微信",
            "category_name": "社交通讯",
            "category_key": "social",
            "effective_seconds": 1800,
            "duration_seconds": 1800,
        },
    ]

    widget.set_sessions(sessions, {"Code.exe": "VS Code", "WeChat.exe": "微信"})
    widget.show()
    app.processEvents()

    assert len(widget._rows) == 1
    labels = [label.text() for label in widget._rows[0].findChildren(QLabel)]
    assert any("微信" in text for text in labels)
    assert any("10:00 - 10:30" in text for text in labels)
    assert any("30分钟" in text for text in labels)
    assert any("社交通讯" in text for text in labels)


def test_timeline_widget_orders_sessions_by_value_and_compresses_title():
    app = _app()
    widget = TimelineWidget(max_rows=5, min_effective_seconds=600, sort_by_value=True)
    sessions = [
        {
            "start_time": "2026-06-02 17:10:00",
            "end_time": "2026-06-02 18:00:00",
            "process_name": "chrome.exe",
            "window_title": "ChatGPT - Google Chrome",
            "normalized_title": "ChatGPT",
            "category_name": "工作学习",
            "category_key": "ai_tools",
            "effective_seconds": 3000,
            "duration_seconds": 3000,
        },
        {
            "start_time": "2026-06-02 14:23:00",
            "end_time": "2026-06-02 15:45:00",
            "process_name": "Codex.exe",
            "window_title": "Codex",
            "normalized_title": "Codex",
            "category_name": "工作学习",
            "category_key": "coding",
            "effective_seconds": 4920,
            "duration_seconds": 4920,
        },
    ]

    widget.set_sessions(sessions, {"chrome.exe": "Chrome", "Codex.exe": "Codex"})
    widget.show()
    app.processEvents()

    first_labels = [label.text() for label in widget._rows[0].findChildren(QLabel)]
    assert any("Codex" in text for text in first_labels)
    assert any("82分钟" in text for text in first_labels)

    second_labels = [label.text() for label in widget._rows[1].findChildren(QLabel)]
    assert any("Chrome(ChatGPT)" in text for text in second_labels)
    assert any("50分钟" in text for text in second_labels)


def test_key_sessions_use_five_minute_minimum():
    app = _app()
    widget = SessionTop3Widget()
    sessions = [
        {
            "start_time": "2026-08-08 09:00:00",
            "end_time": "2026-08-08 09:05:00",
            "process_name": "Code.exe",
            "category_name": "工作学习",
            "category_key": "coding",
            "effective_seconds": 300,
        },
        {
            "start_time": "2026-08-08 10:00:00",
            "end_time": "2026-08-08 10:04:59",
            "process_name": "notes.exe",
            "category_name": "工作学习",
            "category_key": "office",
            "effective_seconds": 299,
        },
    ]

    widget.set_sessions(sessions)
    app.processEvents()

    assert [session["process_name"] for session in widget._sessions] == ["Code.exe"]


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
        [
            [0, 0, 5, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0] * 24,
            [0] * 24,
            [0] * 24,
            [0] * 24,
            [0] * 24,
            [0] * 24,
        ],
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
    assert len(widget.canvas._week_series) == 7
    assert widget._title_label.text() == "时间趋势（分钟）"


def test_trend_canvas_uses_weekly_line_series_for_seven_day_mode():
    canvas = _TrendCanvas()

    canvas.set_series(
        [
            [1] * 24,
            [2] * 24,
            [3] * 24,
            [4] * 24,
            [5] * 24,
            [6] * 24,
            [7] * 24,
        ],
        [""] * 24,
        "7d",
        [],
        [0, 1, 2, 3, 4, 5, 6],
    )

    assert canvas._mode == "7d"
    assert len(canvas._weekday_colors) == 7
    assert len(canvas._week_series) == 7
    assert canvas._compare_points == []
    assert canvas._uses_hour_units() is False
    assert canvas._compute_y_axis_max(111) == 120
    weekday_style = canvas._weekday_line_style(0, False)
    weekend_style = canvas._weekday_line_style(5, True)
    assert weekend_style["width"] > weekday_style["width"]
    assert weekend_style["alpha"] > weekday_style["alpha"]


def test_trend_widget_keeps_thirty_day_mode_unchanged():
    app = _app()
    widget = TrendChartWidget()
    thirty = [float(i % 5) for i in range(30)]
    widget.set_data(
        [0] * 24,
        [0] * 24,
        [[1] * 24 for _ in range(7)],
        thirty,
    )
    widget.show()
    app.processEvents()

    widget._mode_buttons["30d"].click()
    app.processEvents()

    assert widget._mode == "30d"
    assert widget.canvas._mode == "30d"
    assert widget.canvas._points == thirty
    assert widget.canvas._uses_hour_units() is True
def test_timeline_session_label_preserves_full_title_for_font_elision():
    app = _app()
    widget = TimelineWidget()
    long_title = "这是一个非常非常长但不能在数据层按字符截断的窗口标题"

    label = widget._session_display_label(
        {
            "process_name": "demo.exe",
            "normalized_title": long_title,
        }
    )

    assert label == f"demo.exe({long_title})"
    widget.deleteLater()
    app.processEvents()


def test_trusted_insight_card_renders_complete_plain_text_and_waiting_state():
    app = _app()
    card_type = getattr(dashboard_widgets, "TrustedInsightCard", None)
    assert card_type is not None
    card = card_type()
    card.resize(440, 120)
    card.show()
    app.processEvents()

    card.set_insight(
        {
            "title": "你的优势时段是 09:00–11:00",
            "evidence": "ChatGPT、Codex <按纯文本显示>，贡献了 42% 的参与时间。",
            "action": "把最难的任务优先放进这个窗口。",
            "confidence": "medium",
        }
    )
    app.processEvents()

    assert card.title_label.fullText() == "你的优势时段是 09:00–11:00"
    assert card.evidence_label.fullText() == "ChatGPT、Codex <按纯文本显示>，贡献了 42% 的参与时间。"
    assert card.action_label.fullText() == "把最难的任务优先放进这个窗口。"
    assert card.confidence_label.text() == "中可信"
    assert card.maximumHeight() <= 124
    for label in (
        card.title_label,
        card.evidence_label,
        card.action_label,
        card.confidence_label,
    ):
        assert label.textFormat() == Qt.PlainText

    card.set_insight(None)
    app.processEvents()

    assert card.title_label.fullText() == "洞察积累中"
    assert card.evidence_label.fullText() == "继续记录以形成可靠基线"
    assert card.action_label.fullText() == ""
    assert card.confidence_label.text() == "数据不足"

    card.set_insight({"title": "未知置信度", "confidence": "unexpected"})
    assert card.confidence_label.text() == "低可信"
    card.deleteLater()
    app.processEvents()
