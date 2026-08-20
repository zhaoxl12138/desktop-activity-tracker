from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker.gui.widgets.dashboard_widgets import (  # noqa: E402
    ActiveRatioRingWidget,
    DonutChartWidget,
    SessionTop3Widget,
    TimelineWidget,
    TrendChartWidget,
    _TrendCanvas,
)
from daylens.gui.widgets import dashboard_widgets  # noqa: E402


def _app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_rhythm_comparison_card_switches_modes_without_category_legend():
    app = _app()
    card_type = getattr(dashboard_widgets, "RhythmComparisonCard", None)
    assert card_type is not None
    card = card_type()
    payload = {
        "today": {
            "title": "今日工作节奏",
            "status": {"label": "基线7天", "kind": "baseline"},
            "conclusion": "截至14:50，比近期同类日多20分钟",
            "chart": {
                "kind": "cumulative",
                "labels": [f"{hour // 2:02d}:{(hour % 2) * 30:02d}" for hour in range(48)],
                "current": [60 * index for index in range(30)] + [None] * 18,
                "baseline_median": [50 * index for index in range(30)] + [None] * 18,
                "baseline_low": [40 * index for index in range(30)] + [None] * 18,
                "baseline_high": [55 * index for index in range(30)] + [None] * 18,
            },
            "metrics": [
                {"label": "首次参与", "value": "09:00", "delta": "比平时早10分钟"},
                {"label": "最长连续", "value": "50分钟", "delta": "比平时多5分钟"},
                {"label": "明显中断", "value": "1次", "delta": "比平时少1次"},
            ],
        },
        "7d": {
            "title": "近7天工作节奏",
            "status": {"label": "可比较", "kind": "baseline"},
            "conclusion": "过去7个完整日，日均参与1小时",
            "chart": {"kind": "bars", "labels": ["周三", "周四"], "values": [3600, 5400], "average_seconds": 4500},
            "metrics": [],
        },
        "30d": {
            "title": "近30天工作节奏",
            "status": {"label": "数据积累中", "kind": "waiting"},
            "conclusion": "完整周数据仍在积累",
            "chart": {"kind": "weekly", "labels": ["7/13-7/19"], "values": [None]},
            "metrics": [],
        },
    }

    card.set_data(payload)
    card.show()
    app.processEvents()

    assert card._title_label.text() == "今日工作节奏"
    assert card._status_label.text() == "基线7天"
    assert "工作学习" not in card._legend_text()
    assert "娱乐休闲" not in card._legend_text()
    assert all(label.textFormat() == Qt.PlainText for label in card._dynamic_labels())

    card._mode_buttons["7d"].click()
    app.processEvents()
    assert card._mode == "7d"
    assert card._title_label.text() == "近7天工作节奏"
    assert card.canvas._kind == "bars"
    card.deleteLater()
    app.processEvents()


def test_rhythm_canvas_uses_one_color_for_all_recorded_values():
    _app()
    canvas = dashboard_widgets._RhythmCanvas()
    canvas.set_data(
        {
            "kind": "bars",
            "values": [3_600, 2_400, 1_800],
            "value_kinds": ["current", "legacy", "partial"],
        }
    )

    assert canvas._value_color(0).name() == dashboard_widgets.QColor(
        dashboard_widgets.COLORS["primary"]
    ).name()
    assert canvas._value_color(1).name() == dashboard_widgets.QColor(
        dashboard_widgets.COLORS["primary"]
    ).name()
    assert canvas._value_color(2).name() == dashboard_widgets.QColor(
        dashboard_widgets.COLORS["primary"]
    ).name()


def test_rhythm_canvas_limits_dense_date_labels_to_six_positions():
    _app()
    canvas = dashboard_widgets._RhythmCanvas()

    assert canvas._x_label_indices(7) == list(range(7))
    assert canvas._x_label_indices(30) == [0, 6, 12, 18, 24, 29]


def test_rhythm_comparison_card_falls_back_for_legacy_snapshot():
    app = _app()
    card_type = getattr(dashboard_widgets, "RhythmComparisonCard", None)
    assert card_type is not None
    card = card_type()

    card.set_data({})

    assert card._status_label.text() == "数据积累中"
    assert card._conclusion_label.text() == "节奏数据积累中"
    assert card.canvas._state == "empty"
    card.deleteLater()
    app.processEvents()


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


def test_work_episode_widget_renders_topic_apps_and_participation():
    app = _app()
    widget_type = getattr(dashboard_widgets, "WorkEpisodeListWidget", None)
    assert widget_type is not None
    widget = widget_type()
    widget.set_episodes(
        [
            {
                "start_time": "2026-08-12 09:00:00",
                "end_time": "2026-08-12 09:35:00",
                "topic": "DayLens 首页重构",
                "apps": ["Codex", "Chrome"],
                "engaged_seconds": 1_700,
            }
        ]
    )
    widget.show()
    app.processEvents()

    labels = [label.text() for label in widget._row_widgets[0].findChildren(QLabel)]
    assert "DayLens 首页重构" in labels
    assert any("Codex / Chrome" in text for text in labels)
    assert any("09:00–09:35" in text for text in labels)
    assert any("参与 28分20秒" in text for text in labels)
    assert all(label.textFormat() == Qt.PlainText for label in widget._row_widgets[0].findChildren(QLabel))

    row = widget._row_widgets[0]
    topic_label = row.findChild(QLabel, "workEpisodeTopic")
    app_label = row.findChild(QLabel, "workEpisodeApps")
    time_label = row.findChild(QLabel, "workEpisodeTime")
    duration_label = row.findChild(QLabel, "workEpisodeDuration")
    assert topic_label is not None
    assert app_label is not None
    assert time_label is not None
    assert duration_label is not None
    assert "font-size: 13px" in topic_label.styleSheet()
    assert "font-weight: 800" in topic_label.styleSheet()
    assert dashboard_widgets.COLORS["text"] in topic_label.styleSheet()
    assert "font-size: 11px" in app_label.styleSheet()
    assert dashboard_widgets.COLORS["text_secondary"] in app_label.styleSheet()
    assert "font-size: 11px" in time_label.styleSheet()
    assert "font-weight: 700" in time_label.styleSheet()
    assert dashboard_widgets.COLORS["primary_hover"] in time_label.styleSheet()
    assert "font-size: 12px" in duration_label.styleSheet()
    assert "font-weight: 800" in duration_label.styleSheet()
    assert dashboard_widgets.COLORS["primary"] in duration_label.styleSheet()
    widget.deleteLater()
    app.processEvents()


def test_work_episode_widget_uses_compact_accented_rows_and_hides_duplicate_app():
    app = _app()
    widget = dashboard_widgets.WorkEpisodeListWidget()
    widget.set_episodes(
        [
            {
                "start_time": "2026-08-20 08:22:00",
                "end_time": "2026-08-20 08:41:00",
                "topic": "ChatGPT.exe",
                "apps": ["ChatGPT.exe"],
                "engaged_seconds": 615,
            }
        ]
    )
    widget.show()
    app.processEvents()

    row = widget._row_widgets[0]
    accent = row.findChild(QFrame, "workEpisodeAccent")
    apps = row.findChild(QLabel, "workEpisodeApps")
    assert row.height() == 72
    assert accent is not None and accent.width() == 3
    assert dashboard_widgets.COLORS["coding_green"] in accent.styleSheet()
    assert apps is not None and apps.isHidden()
    assert widget.height() == 72

    widget.deleteLater()
    app.processEvents()


def test_work_episode_widget_keeps_distinct_multi_app_chain():
    app = _app()
    widget = dashboard_widgets.WorkEpisodeListWidget()
    widget.set_episodes(
        [
            {
                "start_time": "2026-08-20 09:00:00",
                "end_time": "2026-08-20 09:20:00",
                "topic": "整理设计方案",
                "apps": ["Obsidian", "ChatGPT.exe"],
                "engaged_seconds": 900,
            }
        ]
    )
    widget.show()
    app.processEvents()

    apps = widget._row_widgets[0].findChild(QLabel, "workEpisodeApps")
    assert apps is not None
    assert apps.text() == "Obsidian / ChatGPT.exe"
    assert apps.isVisible()

    widget.deleteLater()
    app.processEvents()


def test_work_episode_widget_hides_episodes_at_or_below_five_minutes():
    app = _app()
    widget = dashboard_widgets.WorkEpisodeListWidget()
    widget.set_episodes(
        [
            {"seconds": 300, "topic": "exactly five minutes"},
            {"seconds": 301, "topic": "over five minutes"},
        ]
    )
    app.processEvents()

    assert [episode["seconds"] for episode in widget._episodes] == [301]
    assert len(widget._row_widgets) == 1
    widget.deleteLater()
    app.processEvents()


def test_trusted_insight_card_collapses_low_confidence_and_expands_high_confidence():
    app = _app()
    card = dashboard_widgets.TrustedInsightCard()
    card.set_insight(
        {
            "title": "先让数据口径稳定",
            "evidence": "旧计量口径占比超过20%",
            "action": "继续记录",
            "confidence": "low",
        }
    )
    app.processEvents()

    assert card.maximumHeight() <= 72
    assert card.action_label.isHidden()
    assert card.evidence_label.maxLines() == 1

    card.set_insight(
        {
            "title": "你的优势时段是 09:00–11:00",
            "evidence": "最近14天证据充分",
            "action": "保护这个时间窗口",
            "confidence": "high",
        }
    )
    app.processEvents()

    assert card.maximumHeight() >= 110
    assert not card.action_label.isHidden()
    card.deleteLater()
    app.processEvents()


def test_top_app_widget_keeps_compact_single_line_rows_without_overlap():
    app = _app()
    widget = dashboard_widgets.TopAppListWidget()
    widget.set_items(
        [
            {
                "process_name": "chrome.exe",
                "display_name": "Chrome",
                "seconds": 900,
                "engaged_seconds": 700,
                "passive_seconds": 0,
                "purpose": "RK3568 文档",
                "icon": None,
            }
        ]
    )
    widget.show()
    app.processEvents()

    labels = [label.text() for label in widget._row_widgets[0].findChildren(QLabel)]
    assert "Chrome" in labels
    assert "RK3568 文档" not in labels
    assert "15分0秒" in labels
    assert not any("前台" in text or "参与" in text or "被动" in text for text in labels)
    assert len(labels) == 4
    assert widget._row_widgets[0].minimumHeight() <= 32
    widget.deleteLater()
    app.processEvents()


def test_top_app_widget_limits_dashboard_ranking_to_five_rows():
    app = _app()
    widget = dashboard_widgets.TopAppListWidget()
    widget.set_items(
        [
            {
                "process_name": f"app{index}.exe",
                "display_name": f"App {index}",
                "seconds": 600 - index,
                "icon": None,
            }
            for index in range(8)
        ]
    )
    widget.show()
    app.processEvents()

    assert widget.MAX_ROWS == 5
    assert len(widget._row_widgets) == 5
    widget.deleteLater()
    app.processEvents()


def test_daily_goals_card_renders_only_work_and_entertainment_rows():
    app = _app()
    card_type = getattr(dashboard_widgets, "DailyGoalsCard", None)
    assert card_type is not None
    card = card_type()
    card.set_data(
        {
            "status": {"label": "智能目标", "kind": "ready"},
            "work": {
                "current_seconds": 3_600,
                "target_seconds": 6_300,
                "remaining_seconds": 2_700,
                "progress_percent": 57,
                "sample_count": 7,
                "comparable": True,
            },
            "entertainment": {
                "current_seconds": 900,
                "limit_seconds": 3_600,
                "progress_percent": 25,
                "state": "within",
            },
            "advice": "再完成一个25分钟工作段，继续接近今日目标",
        }
    )
    card.show()
    app.processEvents()

    assert "1小时 / 1小时45分钟" in card.work_value_label.text()
    assert "15分钟 / 1小时" in card.entertainment_value_label.text()
    assert card.work_bar.value() == 57
    assert card.entertainment_bar.value() == 25
    visible_text = {
        label.text()
        for label in card.findChildren(QLabel)
        if not label.isHidden()
    }
    assert "智能目标" not in visible_text
    assert "再完成一个25分钟工作段，继续接近今日目标" not in visible_text

    card.set_data({})
    assert card.work_value_label.text() == "目标数据积累中"
    assert card.entertainment_value_label.text() == "尚未设置"
    card.deleteLater()
    app.processEvents()


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


def test_donut_and_thirty_day_trend_expose_attention_semantics():
    app = _app()
    donut = DonutChartWidget()
    donut.set_data(
        3_600,
        [
            ("参与", 1_800, "#00ff00"),
            ("被动媒体", 1_200, "#ff9900"),
            ("挂机/空闲", 600, "#999999"),
        ],
        primary_seconds=1_800,
        primary_label="参与时长",
    )

    assert donut._total_seconds == 3_600
    assert donut._primary_seconds == 1_800
    assert donut._primary_label == "参与时长"

    trend = TrendChartWidget()
    trend.set_data(
        [0] * 24,
        [0] * 24,
        [[0] * 24 for _ in range(7)],
        [0.5] * 30,
        thirty_day_metric="engaged",
    )
    trend.set_mode("30d")
    assert "每日参与时间" in trend._cmp_legend.text()
    assert trend._title_label.text() == "参与时间趋势（小时）"

    trend.set_data(
        [0] * 24,
        [0] * 24,
        [[0] * 24 for _ in range(7)],
        [1.0] * 30,
        thirty_day_metric="effective",
    )
    assert "每日有效时间" in trend._cmp_legend.text()
    assert trend._title_label.text() == "有效时间趋势（小时）"

    ratio_ring = ActiveRatioRingWidget()
    assert ratio_ring._ratio_label == "有效时间占比"
    donut.deleteLater()
    ratio_ring.deleteLater()
    trend.deleteLater()
    app.processEvents()


def test_thirty_day_canvas_preserves_gaps_and_splits_line_segments():
    _app()
    canvas = _TrendCanvas()

    canvas.set_series(
        [None, 1.0, 2.0, None, 3.0],
        mode="30d",
    )

    assert canvas._points == [None, 1.0, 2.0, None, 3.0]
    assert canvas._series_state() == "chart"
    assert canvas._numeric_segments(canvas._points) == [
        [(1, 1.0), (2, 2.0)],
        [(4, 3.0)],
    ]


def test_metric_break_notice_takes_priority_over_classification_notice():
    _app()
    trend = TrendChartWidget()

    trend.set_history_comparability(
        metric_break=True,
        classification_comparable=False,
    )

    assert not trend.classification_notice.isHidden()
    assert trend.classification_notice.text() == (
        "计量口径已变化，历史参与趋势暂不可比"
    )

    trend.set_history_comparability(
        metric_break=False,
        classification_comparable=False,
    )
    assert trend.classification_notice.text() == (
        "分类规则已变化，分类趋势暂不可比"
    )

    trend.deleteLater()


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
