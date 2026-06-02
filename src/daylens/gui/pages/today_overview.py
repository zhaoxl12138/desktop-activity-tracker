"""Dashboard home page."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import psutil
from PySide6.QtCore import QFileInfo, QTimer
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
from .. import style as ui_style
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
        self.time_stats_labels: dict[str, QLabel] = {}
        self._icon_provider = QFileIconProvider()
        self._icon_cache: dict[str, QIcon | None] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(10)
        metrics_grid.setVerticalSpacing(0)
        root.addLayout(metrics_grid)
        for column, (key, title, icon, color) in enumerate(
            [
                ("total", "总使用时长", "T", ui_style.COLORS["primary"]),
                ("work", "学习/工作时长", "W", ui_style.COLORS["coding_green"]),
                ("ent", "娱乐时长", "E", ui_style.COLORS["video_orange"]),
                ("social", "社交通讯时长", "S", ui_style.COLORS["social_purple"]),
                ("idle", "挂机时长", "I", ui_style.COLORS["idle_gray"]),
            ]
        ):
            card = MetricCard(title, icon, color)
            self.metric_cards[key] = card
            metrics_grid.addWidget(card, 0, column)

        middle_grid = QGridLayout()
        middle_grid.setHorizontalSpacing(10)
        middle_grid.setVerticalSpacing(8)
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

        bottom_grid.setRowStretch(0, 1)
        bottom_grid.setRowStretch(1, 1)
        for column in range(11):
            stretch = 2 if column < 5 else 1
            middle_grid.setColumnStretch(column, stretch)
            bottom_grid.setColumnStretch(column, stretch)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)
        self.refresh()

    def _build_distribution_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(ui_style.get_dashboard_card_style())
        card.setFixedHeight(220)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        title = QLabel("时间分布")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {ui_style.COLORS['text']};")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.donut_widget = DonutChartWidget()
        row.addWidget(self.donut_widget, 1)

        right_layout = QVBoxLayout()
        self.legend_widget = DistributionLegend()
        right_layout.addWidget(self.legend_widget, 1)
        self.active_ratio_label = QLabel("活跃时间占比：-")
        self.active_ratio_label.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {ui_style.COLORS['primary']};"
        )
        right_layout.addWidget(self.active_ratio_label)
        row.addLayout(right_layout, 1)

        layout.addLayout(row)
        return card

    def _build_time_stats_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(ui_style.get_dashboard_card_style())
        card.setFixedHeight(220)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        title = QLabel("时间统计")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {ui_style.COLORS['text']};")
        layout.addWidget(title)

        for key, label_text in [
            ("total", "总时长"),
            ("active", "活跃时长"),
            ("idle", "挂机时长"),
            ("ratio", "活跃时间占比"),
        ]:
            row = QHBoxLayout()
            name_label = QLabel(label_text)
            name_label.setStyleSheet(f"font-size: 14px; color: {ui_style.COLORS['text_secondary']};")
            value_label = QLabel("--")
            value_label.setStyleSheet(f"font-size: 14px; color: {ui_style.COLORS['text']}; font-weight: 700;")
            row.addWidget(name_label)
            row.addStretch()
            row.addWidget(value_label)
            layout.addLayout(row)
            self.time_stats_labels[key] = value_label

        layout.addStretch()
        return card

    def _build_focus_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(ui_style.get_dashboard_card_style())
        card.setFixedHeight(220)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("今日专注")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {ui_style.COLORS['text']};")
        header.addWidget(title)
        header.addStretch()
        self.consecutive_label = QLabel("")
        self.consecutive_label.setStyleSheet(
            f"font-size: 11px; color: {ui_style.COLORS['primary']}; font-weight: 700;"
        )
        header.addWidget(self.consecutive_label)
        layout.addLayout(header)

        self.focus_hint = QLabel("今日暂未识别到连续专注时段。")
        self.focus_hint.setWordWrap(True)
        self.focus_hint.setStyleSheet(f"font-size: 13px; color: {ui_style.COLORS['text_secondary']};")
        layout.addWidget(self.focus_hint)
        layout.addStretch()
        return card

    def _build_focus_timeline_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(ui_style.get_dashboard_card_style())
        card.setMinimumHeight(300)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("今日专注时间轴")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {ui_style.COLORS['text']};")
        layout.addWidget(title)

        self.focus_axis = FocusTimelineBarWidget()
        layout.addWidget(self.focus_axis)

        tick_row = QHBoxLayout()
        for index, text in enumerate(["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"]):
            label = QLabel(text)
            label.setStyleSheet(f"font-size: 11px; color: {ui_style.COLORS['text_muted']};")
            tick_row.addWidget(label)
            if index < 6:
                tick_row.addStretch()
        layout.addLayout(tick_row)

        legend_row = QHBoxLayout()
        for name, color in [
            ("学习/工作", ui_style.COLORS["coding_green"]),
            ("视频娱乐", ui_style.COLORS["video_orange"]),
            ("社交通讯", ui_style.COLORS["social_purple"]),
            ("其他", ui_style.COLORS["ai_blue"]),
            ("离开/空闲", ui_style.COLORS["idle_gray"]),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size: 12px; color: {color};")
            text_label = QLabel(name)
            text_label.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};")
            legend_row.addWidget(dot)
            legend_row.addWidget(text_label)
            legend_row.addSpacing(10)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        self.timeline_widget = TimelineWidget(max_rows=6)
        layout.addWidget(self.timeline_widget, 1)
        return card

    def refresh(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        stats = database.query_date_stats(self.db_path, today)
        totals = stats.get("totals", {})
        effective = totals.get("effective_seconds", 0) or 0
        idle_seconds = totals.get("idle_seconds", 0) or 0
        total_seconds = effective + idle_seconds

        work_seconds, social_seconds, entertainment_seconds = self._category_stats(stats)
        other_seconds = max(effective - work_seconds - social_seconds - entertainment_seconds, 0)
        history = self._load_metric_history(8)
        self._update_metrics(
            total_seconds,
            work_seconds,
            entertainment_seconds,
            social_seconds,
            idle_seconds,
            history,
        )

        distribution = [
            ("学习/工作", work_seconds, ui_style.COLORS["coding_green"]),
            ("视频娱乐", entertainment_seconds, ui_style.COLORS["video_orange"]),
            ("社交通讯", social_seconds, ui_style.COLORS["social_purple"]),
            ("挂机", idle_seconds, ui_style.COLORS["idle_gray"]),
            ("其他", other_seconds, ui_style.COLORS["ai_blue"]),
        ]
        self.donut_widget.set_data(total_seconds, distribution)
        self.legend_widget.set_items(distribution, total_seconds)

        active_ratio = int(round((effective / total_seconds) * 100)) if total_seconds else 0
        self.active_ratio_label.setText(f"活跃时间占比：{active_ratio}%")
        self.time_stats_labels["total"].setText(_compact_duration(total_seconds))
        self.time_stats_labels["active"].setText(_compact_duration(effective))
        self.time_stats_labels["idle"].setText(_compact_duration(idle_seconds))
        self.time_stats_labels["ratio"].setText(f"{active_ratio}%")

        sessions = query_today_sessions(self.db_path, today)
        self.timeline_widget.set_sessions(sessions, self.display_name_mapping)
        self.focus_axis.set_minutes(self._build_focus_axis(sessions))
        self.trend_card.set_data(*self._build_trend_data(sessions))
        self._update_focus_summary(today)
        self._update_top_apps(stats)

    def _update_focus_summary(self, today: str) -> None:
        blocks = timeline.identify_focus_blocks(timeline.build_timeline(self.db_path, today))
        if blocks:
            best = max(blocks, key=lambda block: block.duration_minutes)
            self.focus_hint.setText(
                f"最长专注：{best.start_slot}-{best.end_slot}，{best.duration_minutes}分钟，{best.main_category}"
            )
        else:
            self.focus_hint.setText("今日暂未识别到连续专注时段。")

        consecutive_days = count_consecutive_days(self.db_path)
        self.consecutive_label.setText(f"第 {consecutive_days} 天" if consecutive_days > 0 else "")

    def _update_top_apps(self, stats: dict) -> None:
        merged: dict[str, dict[str, object]] = {}
        for item in stats.get("by_app", []):
            process_name = item.get("process_name") or "Unknown"
            display_name = self._resolve_display(process_name, stats.get("by_app_detail", []))
            seconds = item.get("effective_seconds", 0) or 0
            if display_name not in merged:
                merged[display_name] = {"process": process_name, "seconds": 0}
            merged[display_name]["seconds"] = int(merged[display_name]["seconds"]) + seconds

        rows = []
        for display_name, info in sorted(merged.items(), key=lambda item: -int(item[1]["seconds"]))[:5]:
            process_name = str(info["process"])
            rows.append((process_name, display_name, int(info["seconds"]), self._app_icon(process_name)))
        self.top_app_card.set_items(rows)

    def _app_icon(self, process_name: str) -> QIcon | None:
        cache_key = process_name.lower()
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]

        exe_path = self._find_exe_path(process_name)
        icon = self._icon_provider.icon(QFileInfo(exe_path)) if exe_path else None
        self._icon_cache[cache_key] = icon
        return icon

    def _find_exe_path(self, process_name: str) -> str | None:
        for proc in psutil.process_iter(attrs=["name", "exe"]):
            try:
                if (proc.info.get("name") or "").lower() == process_name.lower():
                    exe_path = proc.info.get("exe")
                    if exe_path and os.path.exists(exe_path):
                        return exe_path
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def _build_focus_axis(self, sessions: list[dict]) -> list[str]:
        colors = [ui_style.COLORS["idle_gray"]] * 1440
        for session in sessions:
            start = self._to_minute(session.get("start_time", ""))
            end = max(start, self._to_minute(session.get("end_time", "")))
            color = self._color_for_category(session.get("category_key") or "other")
            for minute in range(max(0, start), min(1439, end) + 1):
                colors[minute] = color
        return colors

    def _build_trend_data(self, sessions: list[dict]) -> tuple[list[int], list[int], list[int]]:
        # ── Today: aggregate effective minutes per hour (float → round at end)
        hour_minutes = [0.0] * 24
        for session in sessions:
            start_dt = self._parse_dt(session.get("start_time", ""))
            end_dt = self._parse_dt(session.get("end_time", ""))
            eff_sec = float(session.get("effective_seconds", 0) or 0)
            if eff_sec <= 0 or start_dt is None or end_dt is None:
                continue
            total_span = (end_dt - start_dt).total_seconds()
            if total_span <= 0:
                hour_minutes[start_dt.hour] += eff_sec / 60.0
                continue
            curr = start_dt
            while curr < end_dt:
                hour = curr.hour
                next_hour = curr.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                seg_end = min(end_dt, next_hour)
                seg_span = (seg_end - curr).total_seconds()
                hour_minutes[hour] += (eff_sec / 60.0) * (seg_span / total_span)
                curr = seg_end
        today_series = [int(round(v)) for v in hour_minutes]

        # ── 7d / 30d: daily aggregation from DB
        today_date = date.today()
        seven_days = [(today_date - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(6, -1, -1)]
        thirty_days = [(today_date - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(29, -1, -1)]
        seven_day_stats = database.query_date_range_stats(self.db_path, seven_days)
        thirty_day_stats = database.query_date_range_stats(self.db_path, thirty_days)
        seven_day_series = [
            int(round((item.get("effective_seconds", 0) or 0) / 60.0))
            for item in seven_day_stats.get("daily", [])
        ]
        thirty_day_series = [
            int(round((item.get("effective_seconds", 0) or 0) / 60.0))
            for item in thirty_day_stats.get("daily", [])
        ]
        return today_series, seven_day_series, thirty_day_series

    def _to_minute(self, timestamp: str) -> int:
        try:
            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            return dt.hour * 60 + dt.minute
        except Exception:
            return 0

    def _parse_dt(self, timestamp: str) -> datetime | None:
        try:
            return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    def _category_stats(self, stats: dict) -> tuple[int, int, int]:
        work_keys = {"ai_tools", "coding", "reading", "creative"}
        work_seconds = 0
        social_seconds = 0
        entertainment_seconds = 0
        for item in stats.get("by_category", []):
            seconds = item.get("effective_seconds", 0) or 0
            category_key = item.get("category_key")
            if category_key in work_keys:
                work_seconds += seconds
            elif category_key == "social":
                social_seconds += seconds
            elif category_key in {"video", "gaming"}:
                entertainment_seconds += seconds
        return work_seconds, social_seconds, entertainment_seconds

    def _color_for_category(self, category_key: str) -> str:
        if category_key in {"ai_tools", "coding", "reading", "creative"}:
            return ui_style.COLORS["coding_green"]
        if category_key in {"video", "gaming"}:
            return ui_style.COLORS["video_orange"]
        if category_key == "social":
            return ui_style.COLORS["social_purple"]
        if category_key in {"idle", "idle_leave"}:
            return ui_style.COLORS["idle_gray"]
        return ui_style.COLORS["ai_blue"]

    def _resolve_display(self, process_name: str, app_details: list[dict]) -> str:
        mapped_name = self.display_name_mapping.get(process_name)
        if mapped_name and mapped_name != process_name:
            return mapped_name

        wrapper_processes = {"WindowsTerminal.exe", "cmd.exe", "powershell.exe", "Code.exe", "Cursor.exe"}
        if process_name not in wrapper_processes:
            return mapped_name or process_name

        top_title = ""
        top_seconds = 0
        for detail in app_details:
            if detail.get("process_name") != process_name:
                continue
            seconds = detail.get("effective_seconds", 0) or 0
            if seconds > top_seconds:
                top_seconds = seconds
                top_title = detail.get("window_title", "") or ""

        for keyword, label in [("Codex", "Codex"), ("Cursor", "Cursor"), ("Claude Code", "Claude Code")]:
            if keyword.lower() in top_title.lower():
                return label
        return mapped_name or process_name

    def _load_metric_history(self, days: int) -> list[dict]:
        today_date = datetime.now().date()
        result = []
        for offset in range(days - 1, -1, -1):
            day = today_date - timedelta(days=offset)
            stats = database.query_date_stats(self.db_path, day.strftime("%Y-%m-%d"))
            totals = stats.get("totals", {})
            effective = totals.get("effective_seconds", 0) or 0
            idle_seconds = totals.get("idle_seconds", 0) or 0
            work_seconds, social_seconds, entertainment_seconds = self._category_stats(stats)
            result.append(
                {
                    "total": effective + idle_seconds,
                    "work": work_seconds,
                    "ent": entertainment_seconds,
                    "social": social_seconds,
                    "idle": idle_seconds,
                }
            )
        return result

    def _update_metrics(
        self,
        total_seconds: int,
        work_seconds: int,
        entertainment_seconds: int,
        social_seconds: int,
        idle_seconds: int,
        history: list[dict],
    ) -> None:
        values = {
            "total": total_seconds,
            "work": work_seconds,
            "ent": entertainment_seconds,
            "social": social_seconds,
            "idle": idle_seconds,
        }
        for key, current in values.items():
            yesterday = history[-2].get(key, 0) if len(history) >= 2 else 0
            diff = current - yesterday
            if diff == 0:
                delta_text = "较昨日 持平"
            else:
                direction = "↑" if diff > 0 else "↓"
                delta_text = f"较昨日 {direction} {_compact_duration(abs(diff))}"
            self.metric_cards[key].set_value(_compact_duration(current), delta_text)
            self.metric_cards[key].set_sparkline([item[key] for item in history])
        self.metric_cards["ent"].set_warning(entertainment_seconds > 5400)


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
