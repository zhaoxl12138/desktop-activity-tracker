"""Dashboard home page."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import os

import psutil
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFileIconProvider,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ... import database, timeline
from ...database import count_consecutive_days, query_today_sessions
from ..style import COLORS, DASHBOARD_CARD_STYLE
from ..widgets.dashboard_widgets import (
    DistributionLegend,
    DonutChartWidget,
    FocusTimelineBarWidget,
    MetricCard,
    TimelineWidget,
    TopAppListWidget,
    TrendChartWidget,
)


class TodayOverviewPage(QWidget):
    def __init__(self, db_path, display_name_mapping=None):
        super().__init__()
        self.db_path = db_path
        self.display_name_mapping = display_name_mapping or {}
        self.metric_cards: dict[str, MetricCard] = {}
        self._icon_provider = QFileIconProvider()
        self._icon_cache: dict[str, QIcon | None] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(10)
        root.addLayout(metrics_grid)
        for col, (key, title, icon, color) in enumerate(
            [
                ("total", "总使用时长", "🕒", COLORS["primary"]),
                ("work", "学习/工作时长", "📚", COLORS["coding_green"]),
                ("ent", "娱乐时长", "🎮", COLORS["video_orange"]),
                ("social", "社交通讯时长", "💬", COLORS["social_purple"]),
                ("idle", "挂机时长", "☕", COLORS["idle_gray"]),
            ]
        ):
            card = MetricCard(title, icon, color)
            self.metric_cards[key] = card
            metrics_grid.addWidget(card, 0, col)

        middle_grid = QGridLayout()
        middle_grid.setHorizontalSpacing(10)
        root.addLayout(middle_grid)
        middle_grid.addWidget(self._build_distribution_card(), 0, 0, 1, 5)
        middle_grid.addWidget(self._build_time_stats_card(), 0, 5, 1, 3)
        middle_grid.addWidget(self._build_focus_card(), 0, 8, 1, 3)

        bottom_grid = QGridLayout()
        bottom_grid.setHorizontalSpacing(10)
        bottom_grid.setVerticalSpacing(10)
        root.addLayout(bottom_grid, 1)
        bottom_grid.addWidget(self._build_focus_timeline_card(), 0, 0, 2, 7)
        self.trend_card = TrendChartWidget()
        bottom_grid.addWidget(self.trend_card, 0, 7, 1, 4)
        self.top_app_card = TopAppListWidget()
        bottom_grid.addWidget(self.top_app_card, 1, 7, 1, 4)

        for col in range(11):
            weight = 2 if col <= 4 else 1
            middle_grid.setColumnStretch(col, weight)
            bottom_grid.setColumnStretch(col, weight)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)
        self.refresh()

    def _build_distribution_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(DASHBOARD_CARD_STYLE)
        card.setFixedHeight(235)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel("时间分布")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        layout.addWidget(title)
        row = QHBoxLayout()
        self.donut_widget = DonutChartWidget()
        row.addWidget(self.donut_widget, 1)
        right = QVBoxLayout()
        self.legend_widget = DistributionLegend()
        right.addWidget(self.legend_widget, 1)
        self.active_ratio_label = QLabel("活跃时间占比：-")
        self.active_ratio_label.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {COLORS['primary']};")
        right.addWidget(self.active_ratio_label)
        row.addLayout(right, 1)
        layout.addLayout(row)
        return card

    def _build_time_stats_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(DASHBOARD_CARD_STYLE)
        card.setFixedHeight(235)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        title = QLabel("时间统计")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        layout.addWidget(title)
        self.time_stats_labels = {}
        for key, text in [("total", "总时长"), ("active", "活跃时长"), ("idle", "挂机时长"), ("ratio", "活跃时间占比")]:
            row = QHBoxLayout()
            left = QLabel(text)
            left.setStyleSheet(f"font-size: 14px; color: {COLORS['text_secondary']};")
            val = QLabel("--")
            val.setStyleSheet(f"font-size: 14px; color: {COLORS['text']}; font-weight: 700;")
            row.addWidget(left)
            row.addStretch()
            row.addWidget(val)
            layout.addLayout(row)
            self.time_stats_labels[key] = val
        layout.addStretch()
        return card

    def _build_focus_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(DASHBOARD_CARD_STYLE)
        card.setFixedHeight(235)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        header = QHBoxLayout()
        title = QLabel("今日专注")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        self.consecutive_label = QLabel("")
        self.consecutive_label.setStyleSheet(f"font-size: 11px; color: {COLORS['primary']}; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.consecutive_label)
        layout.addLayout(header)
        self.focus_hint = QLabel("今日暂未识别到连续专注时段。")
        self.focus_hint.setWordWrap(True)
        self.focus_hint.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        layout.addWidget(self.focus_hint)
        layout.addStretch()
        return card

    def _build_focus_timeline_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(DASHBOARD_CARD_STYLE)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel("今日专注时间轴")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        layout.addWidget(title)
        self.focus_axis = FocusTimelineBarWidget()
        layout.addWidget(self.focus_axis)
        ticks = QHBoxLayout()
        for t in ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"]:
            lab = QLabel(t)
            lab.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
            ticks.addWidget(lab)
            if t != "24:00":
                ticks.addStretch()
        layout.addLayout(ticks)
        legend = QHBoxLayout()
        for name, color in [
            ("学习/工作", COLORS["coding_green"]),
            ("视频娱乐", COLORS["video_orange"]),
            ("社交通讯", COLORS["social_purple"]),
            ("其他", COLORS["ai_blue"]),
            ("离开/空闲", COLORS["idle_gray"]),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size: 12px; color: {color};")
            txt = QLabel(name)
            txt.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
            legend.addWidget(dot)
            legend.addWidget(txt)
            legend.addSpacing(10)
        legend.addStretch()
        layout.addLayout(legend)
        self.timeline_widget = TimelineWidget(max_rows=6)
        layout.addWidget(self.timeline_widget, 1)
        return card

    def refresh(self):
        today = datetime.now().strftime("%Y-%m-%d")
        stats = database.query_date_stats(self.db_path, today)
        totals = stats.get("totals", {})
        effective = totals.get("effective_seconds", 0) or 0
        idle_sec = totals.get("idle_seconds", 0) or 0
        total_sec = effective + idle_sec
        work_sec, social_sec, ent_sec = self._category_stats(stats)
        other_sec = max(effective - work_sec - social_sec - ent_sec, 0)

        history = self._load_metric_history(8)
        self._update_metrics(total_sec, work_sec, ent_sec, social_sec, idle_sec, history)
        distribution = [
            ("学习/工作", work_sec, COLORS["coding_green"]),
            ("视频娱乐", ent_sec, COLORS["video_orange"]),
            ("社交通讯", social_sec, COLORS["social_purple"]),
            ("挂机", idle_sec, COLORS["idle_gray"]),
            ("其他", other_sec, COLORS["ai_blue"]),
        ]
        self.donut_widget.set_data(total_sec, distribution)
        self.legend_widget.set_items(distribution, total_sec)
        active_ratio = int(round((effective / total_sec) * 100)) if total_sec else 0
        self.active_ratio_label.setText(f"活跃时间占比：{active_ratio}%")
        self.time_stats_labels["total"].setText(_compact_duration(total_sec))
        self.time_stats_labels["active"].setText(_compact_duration(effective))
        self.time_stats_labels["idle"].setText(_compact_duration(idle_sec))
        self.time_stats_labels["ratio"].setText(f"{active_ratio}%")

        sessions = query_today_sessions(self.db_path, today)
        self.timeline_widget.set_sessions(sessions, self.display_name_mapping)
        self.focus_axis.set_minutes(self._build_focus_axis(sessions))
        self.trend_card.set_data(*self._build_trend_data(sessions))
        self._update_focus_summary(today)
        self._update_top_apps(stats)

    def _update_focus_summary(self, today: str):
        tl = timeline.build_timeline(self.db_path, today)
        blocks = timeline.identify_focus_blocks(tl)
        if blocks:
            best = max(blocks, key=lambda x: x.duration_minutes)
            self.focus_hint.setText(f"最长专注：{best.start_slot}-{best.end_slot}，{best.duration_minutes}分钟，{best.main_category}")
        else:
            self.focus_hint.setText("今日暂未识别到连续专注时段。")
        cons = count_consecutive_days(self.db_path)
        self.consecutive_label.setText(f"第 {cons} 天" if cons > 0 else "")

    def _update_top_apps(self, stats):
        merged: dict[str, dict] = {}
        for item in stats.get("by_app", []):
            process = item.get("process_name") or "Unknown"
            display = self._resolve_display(process, stats.get("by_app_detail", []))
            secs = item.get("effective_seconds", 0) or 0
            if display not in merged:
                merged[display] = {"process": process, "seconds": 0}
            merged[display]["seconds"] += secs
        top = sorted(merged.items(), key=lambda x: -x[1]["seconds"])[:5]
        rows = []
        for display, info in top:
            process = info["process"]
            icon = self._app_icon(process)
            rows.append((process, display, info["seconds"], icon))
        self.top_app_card.set_items(rows)

    def _app_icon(self, process_name: str) -> QIcon | None:
        key = process_name.lower()
        if key in self._icon_cache:
            return self._icon_cache[key]
        exe = self._find_exe_path(process_name)
        icon = self._icon_provider.icon(exe) if exe else None
        self._icon_cache[key] = icon
        return icon

    def _find_exe_path(self, process_name: str) -> str | None:
        for proc in psutil.process_iter(attrs=["name", "exe"]):
            try:
                if (proc.info.get("name") or "").lower() == process_name.lower():
                    exe = proc.info.get("exe")
                    if exe and os.path.exists(exe):
                        return exe
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def _build_focus_axis(self, sessions: list[dict]) -> list[str]:
        colors = [COLORS["idle_gray"]] * 1440
        for s in sessions:
            start = self._to_minute(s.get("start_time", ""))
            end = self._to_minute(s.get("end_time", ""))
            if end < start:
                end = start
            color = self._color_for_category(s.get("category_key") or "other")
            for m in range(max(0, start), min(1439, end) + 1):
                colors[m] = color
        return colors

    def _to_minute(self, dt_text: str) -> int:
        try:
            dt = datetime.strptime(dt_text, "%Y-%m-%d %H:%M:%S")
            return dt.hour * 60 + dt.minute
        except Exception:
            return 0

    def _build_trend_data(self, sessions: list[dict]) -> tuple[list[int], list[int], list[int]]:
        today_line = [0] * 25
        for s in sessions:
            h = self._to_minute(s.get("start_time", "")) // 60
            today_line[max(0, min(24, h))] += int((s.get("effective_seconds", 0) or 0) / 60)
        today_obj = date.today()
        d7 = [(today_obj - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        d30 = [(today_obj - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
        r7 = database.query_date_range_stats(self.db_path, d7)
        r30 = database.query_date_range_stats(self.db_path, d30)
        line7 = [int((x.get("effective_seconds", 0) or 0) / 60) for x in r7.get("daily", [])]
        line30 = [int((x.get("effective_seconds", 0) or 0) / 60) for x in r30.get("daily", [])]
        return today_line, line7, line30

    def _category_stats(self, stats: dict) -> tuple[int, int, int]:
        work_keys = {"ai_tools", "coding", "reading", "creative"}
        work_sec = social_sec = ent_sec = 0
        for item in stats.get("by_category", []):
            sec = item.get("effective_seconds", 0) or 0
            key = item.get("category_key")
            if key in work_keys:
                work_sec += sec
            elif key == "social":
                social_sec += sec
            elif key in {"video", "gaming"}:
                ent_sec += sec
        return work_sec, social_sec, ent_sec

    def _color_for_category(self, key: str) -> str:
        if key in {"ai_tools", "coding", "reading", "creative"}:
            return COLORS["coding_green"]
        if key in {"video", "gaming"}:
            return COLORS["video_orange"]
        if key == "social":
            return COLORS["social_purple"]
        if key in {"idle", "idle_leave"}:
            return COLORS["idle_gray"]
        return COLORS["ai_blue"]

    def _resolve_display(self, process_name, app_details):
        pname = process_name or ""
        mapped = self.display_name_mapping.get(pname)
        if mapped and mapped != pname:
            return mapped
        wrapper = {"WindowsTerminal.exe", "cmd.exe", "powershell.exe", "Code.exe", "Cursor.exe"}
        if pname not in wrapper:
            return mapped or pname
        best_title, best_sec = "", 0
        for d in app_details:
            if d.get("process_name") == pname and (d.get("effective_seconds", 0) or 0) > best_sec:
                best_title, best_sec = d.get("window_title", "") or "", d.get("effective_seconds", 0) or 0
        for pattern, label in [("Codex", "Codex"), ("Cursor", "Cursor"), ("Claude Code", "Claude Code")]:
            if pattern.lower() in best_title.lower():
                return label
        return mapped or pname

    def _load_metric_history(self, days: int):
        today = datetime.now().date()
        dates = [today - timedelta(days=idx) for idx in range(days - 1, -1, -1)]
        hist = []
        for dt in dates:
            day = database.query_date_stats(self.db_path, dt.strftime("%Y-%m-%d"))
            totals = day.get("totals", {})
            effective = totals.get("effective_seconds", 0) or 0
            idle_sec = totals.get("idle_seconds", 0) or 0
            work_sec, social_sec, ent_sec = self._category_stats(day)
            hist.append({"total": effective + idle_sec, "work": work_sec, "ent": ent_sec, "social": social_sec, "idle": idle_sec})
        return hist

    def _update_metrics(self, total_sec, work_sec, ent_sec, social_sec, idle_sec, history):
        mapping = {"total": total_sec, "work": work_sec, "ent": ent_sec, "social": social_sec, "idle": idle_sec}
        for key, current in mapping.items():
            yesterday = history[-2].get(key, 0) if len(history) >= 2 else 0
            diff = current - yesterday
            if diff == 0:
                delta = "较昨日 持平"
            else:
                delta = f"较昨日 {'↑' if diff > 0 else '↓'} {_compact_duration(abs(diff))}"
            self.metric_cards[key].set_value(_compact_duration(current), delta)
            self.metric_cards[key].set_sparkline([d[key] for d in history])
        self.metric_cards["ent"].set_warning(ent_sec > 5400)


def _compact_duration(total_seconds: int) -> str:
    total_seconds = int(total_seconds or 0)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"
