"""Dashboard home page."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import psutil
from PySide6.QtCore import QFileInfo, Qt, QTimer
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

from ... import database, get_app_root, timeline
from ...database import count_consecutive_days, query_today_sessions
from .. import style as ui_style
from ..widgets.dashboard_widgets import (
    ActiveRatioRingWidget,
    DistributionLegend,
    DonutChartWidget,
    FocusTimelineBarWidget,
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
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        content_grid = QGridLayout()
        content_grid.setHorizontalSpacing(14)
        content_grid.setVerticalSpacing(14)
        root.addLayout(content_grid, 1)

        content_grid.addWidget(self._build_distribution_card(), 0, 0, 1, 7)
        content_grid.addWidget(self._build_time_stats_card(), 0, 7, 1, 5)
        content_grid.addWidget(self._build_focus_timeline_card(), 1, 0, 2, 7)
        self.trend_card = TrendChartWidget()
        content_grid.addWidget(self.trend_card, 1, 7, 1, 5)
        self.top_app_card = TopAppListWidget()
        content_grid.addWidget(self.top_app_card, 2, 7, 1, 5)

        content_grid.setRowStretch(0, 3)
        content_grid.setRowStretch(1, 3)
        content_grid.setRowStretch(2, 2)
        content_grid.setRowStretch(2, 3)
        for column in range(12):
            content_grid.setColumnStretch(column, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)
        self.refresh()

    def on_sample_updated(self, sample: dict) -> None:
        """Real-time idle status from worker — cursor/window-based persistent timer."""
        is_effective = sample.get("is_effective", True)
        persistent_idle = sample.get("persistent_idle", 0) or 0
        category_key = sample.get("category_key", "") or ""
        audio_playing = sample.get("audio_playing", False)

        if not is_effective:
            self.idle_dot.setStyleSheet(
                f"font-size: 13px; color: {ui_style.COLORS['warning_yellow']}; font-weight: 700;"
            )
            self.idle_status_label.setText(
                f"挂机中 {_compact_duration(int(persistent_idle))}"
            )
        else:
            self.idle_dot.setStyleSheet(
                f"font-size: 13px; color: {ui_style.COLORS['idle_gray']}; font-weight: 700;"
            )
            if persistent_idle > 5:
                parts = [f"空闲 {int(persistent_idle)}s"]
                if category_key == "video":
                    parts.append("| 音频=" + ("有" if audio_playing else "无"))
                self.idle_status_label.setText(" ".join(parts))
            else:
                self.idle_status_label.setText("活跃中")

    def _build_distribution_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(ui_style.get_dashboard_card_style())
        card.setMinimumHeight(288)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        title = QLabel("📊 时间分布")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {ui_style.COLORS['text']};")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(16)
        self.donut_widget = DonutChartWidget()
        self.donut_widget.setFixedWidth(158)
        row.addWidget(self.donut_widget)

        self.legend_widget = DistributionLegend()
        row.addWidget(self.legend_widget, 1)

        layout.addLayout(row, 1)

        # Status bar: active ratio + idle
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.active_dot = QLabel("●")
        self.active_dot.setStyleSheet(
            f"font-size: 13px; color: {ui_style.COLORS['success_green']}; font-weight: 700;"
        )
        status_row.addWidget(self.active_dot)
        self.active_status_label = QLabel("活跃占比 --")
        self.active_status_label.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {ui_style.COLORS['text']};"
        )
        status_row.addWidget(self.active_status_label)
        status_row.addSpacing(16)
        self.idle_dot = QLabel("●")
        self.idle_dot.setStyleSheet(
            f"font-size: 13px; color: {ui_style.COLORS['idle_gray']}; font-weight: 700;"
        )
        status_row.addWidget(self.idle_dot)
        self.idle_status_label = QLabel("挂机 --")
        self.idle_status_label.setStyleSheet(
            f"font-size: 14px; color: {ui_style.COLORS['text_secondary']};"
        )
        status_row.addWidget(self.idle_status_label)
        status_row.addStretch()
        layout.addLayout(status_row)
        return card

    def _build_time_stats_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(ui_style.get_dashboard_card_style())
        card.setMinimumHeight(288)

        outer = QVBoxLayout(card)
        outer.setContentsMargins(22, 18, 22, 12)
        outer.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(13)

        title = QLabel("⏱ 时间统计")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {ui_style.COLORS['text']};")
        left.addWidget(title)

        for key, label_text, icon_text in [
            ("total", "总时长", "⚡"),
            ("active", "活跃时长", "▶"),
            ("idle", "挂机时长", "⏸"),
            ("ratio", "活跃时间占比", "📊"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(10)
            icon = QLabel(icon_text)
            icon.setFixedWidth(18)
            icon.setStyleSheet(f"font-size: 16px; color: {ui_style.COLORS['text_secondary']};")
            name_label = QLabel(label_text)
            name_label.setStyleSheet(f"font-size: 14px; color: {ui_style.COLORS['text']};")
            value_label = QLabel("--")
            value_label.setStyleSheet(f"font-size: 16px; color: {ui_style.COLORS['text']}; font-weight: 800;")
            row.addWidget(icon)
            row.addWidget(name_label)
            row.addStretch()
            row.addWidget(value_label)
            left.addLayout(row)
            self.time_stats_labels[key] = value_label

        left.addStretch()
        top_row.addLayout(left, 1)

        self.time_stats_ratio_ring = ActiveRatioRingWidget()
        top_row.addWidget(self.time_stats_ratio_ring, 0, Qt.AlignCenter)

        outer.addLayout(top_row, 1)

        cmp_row = QHBoxLayout()
        cmp_row.setSpacing(8)
        cmp_title = QLabel("较昨日")
        cmp_title.setStyleSheet(
            f"font-size: 15px; color: {ui_style.COLORS['text_secondary']}; font-weight: 700;"
        )
        cmp_row.addWidget(cmp_title)

        self._day_cmp_labels = {}
        for key, icon, label_text in [
            ("work", "💻", "办公"),
            ("entertainment", "🎬", "娱乐"),
            ("social", "💬", "社交"),
        ]:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 15px;")
            cmp_row.addWidget(icon_label)

            name_label = QLabel(label_text)
            name_label.setStyleSheet(
                f"font-size: 14px; color: {ui_style.COLORS['text_secondary']};"
            )
            cmp_row.addWidget(name_label)

            value_label = QLabel("--")
            value_label.setStyleSheet(
                f"font-size: 15px; color: {ui_style.COLORS['text']}; font-weight: 700;"
            )
            cmp_row.addWidget(value_label)
            self._day_cmp_labels[key] = value_label

        cmp_row.addStretch()
        outer.addLayout(cmp_row)
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

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 10)
        layout.setSpacing(6)

        title = QLabel("今日专注时间轴")
        title.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {ui_style.COLORS['text']};")
        layout.addWidget(title)

        self.focus_axis = FocusTimelineBarWidget()
        layout.addWidget(self.focus_axis)

        tick_row = QHBoxLayout()
        for index, text in enumerate(["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"]):
            label = QLabel(text)
            label.setStyleSheet(f"font-size: 10px; color: {ui_style.COLORS['text_muted']};")
            tick_row.addWidget(label)
            if index < 6:
                tick_row.addStretch()
        layout.addLayout(tick_row)

        legend_row = QHBoxLayout()
        for name, color in [
            ("💻 办公", ui_style.COLORS["coding_green"]),
            ("🎬 视频娱乐", ui_style.COLORS["video_orange"]),
            ("💬 社交通讯", ui_style.COLORS["social_purple"]),
            ("📦 其他", ui_style.COLORS["tools_grey"]),
            ("💤 离开/空闲", ui_style.COLORS["idle_gray"]),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size: 11px; color: {color};")
            text_label = QLabel(name)
            text_label.setStyleSheet(f"font-size: 11px; color: {ui_style.COLORS['text_secondary']};")
            legend_row.addWidget(dot)
            legend_row.addWidget(text_label)
            legend_row.addSpacing(8)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        self.focus_hint = QLabel("今日暂未识别到连续专注时段。")
        self.focus_hint.setStyleSheet(f"font-size: 11px; color: {ui_style.COLORS['text_secondary']};")
        layout.addWidget(self.focus_hint)

        self.consecutive_label = QLabel("")
        self.consecutive_label.setVisible(False)

        self.timeline_widget = TimelineWidget()
        layout.addWidget(self.timeline_widget, 1)
        return card

    def refresh(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        stats = database.query_date_stats(self.db_path, today)
        totals = stats.get("totals", {})
        effective = totals.get("effective_seconds", 0) or 0
        idle_seconds = totals.get("idle_seconds", 0) or 0
        total_seconds = effective + idle_seconds

        work_seconds, social_seconds, entertainment_seconds, tools_seconds = self._category_stats(stats)
        other_seconds = max(effective - work_seconds - social_seconds - entertainment_seconds, 0)
        # Donut chart: active time only — idle shown separately below
        distribution = [
            ("💻 办公", work_seconds, ui_style.COLORS["coding_green"]),
            ("🎬 视频娱乐", entertainment_seconds, ui_style.COLORS["video_orange"]),
            ("💬 社交通讯", social_seconds, ui_style.COLORS["social_purple"]),
        ]
        if other_seconds > 0:
            distribution.append(("📦 其他", other_seconds, ui_style.COLORS["ai_blue"]))

        self.donut_widget.set_data(effective, distribution)
        self.legend_widget.set_items(distribution, effective)

        active_ratio = int(round((effective / total_seconds) * 100)) if total_seconds else 0
        idle_text = _compact_duration(idle_seconds)
        self.active_status_label.setText(f"活跃占比 {active_ratio}%")
        self.idle_status_label.setText(f"挂机 {idle_text}")
        self.time_stats_labels["total"].setText(_compact_duration(total_seconds))
        self.time_stats_labels["active"].setText(_compact_duration(effective))
        self.time_stats_labels["idle"].setText(_compact_duration(idle_seconds))
        self.time_stats_labels["ratio"].setText(f"{active_ratio}%")
        self.time_stats_ratio_ring.set_ratio(active_ratio)

        # Day-over-day category comparison
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_stats = database.query_date_stats(self.db_path, yesterday_str)
        yesterday_work, yesterday_social, yesterday_ent, _ = self._category_stats(yesterday_stats)

        for key, today_val, yesterday_val in [
            ("work", work_seconds, yesterday_work),
            ("entertainment", entertainment_seconds, yesterday_ent),
            ("social", social_seconds, yesterday_social),
        ]:
            delta = today_val - yesterday_val
            label = self._day_cmp_labels[key]
            if today_val == 0 and yesterday_val == 0:
                label.setText("--")
                label.setStyleSheet(
                    f"font-size: 15px; color: {ui_style.COLORS['text_muted']};"
                )
            elif abs(delta) < 60:
                label.setText("→ 持平")
                label.setStyleSheet(
                    f"font-size: 15px; color: {ui_style.COLORS['text_muted']}; font-weight: 700;"
                )
            elif delta > 0:
                label.setText(f"↑ +{_compact_duration(delta)}")
                label.setStyleSheet(
                    f"font-size: 15px; color: {ui_style.COLORS['success_green']}; font-weight: 700;"
                )
            else:
                label.setText(f"↓ {_compact_duration(abs(delta))}")
                label.setStyleSheet(
                    f"font-size: 15px; color: {ui_style.COLORS['danger_red']}; font-weight: 700;"
                )


        sessions = query_today_sessions(self.db_path, today)
        self.timeline_widget.set_sessions(sessions, self.display_name_mapping)
        self.focus_axis.set_minutes(self._build_focus_axis(sessions))
        self.trend_card.set_data(*self._build_trend_data(sessions))  # today, yesterday, 7d, 30d
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
            icon_process = self._icon_process_for_display(process_name, display_name)
            rows.append((process_name, display_name, int(info["seconds"]), self._app_icon(icon_process)))
        self.top_app_card.set_items(rows)

    @staticmethod
    def _icon_process_for_display(process_name: str, display_name: str) -> str:
        resolved_icons = {
            "Codex": "Codex.exe",
            "Claude Code": "claude.exe",
            "Cursor": "Cursor.exe",
        }
        return resolved_icons.get(display_name, process_name)

    def _app_icon(self, process_name: str) -> QIcon | None:
        cache_key = process_name.lower()
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]

        icon_source = self._resolve_icon_source(process_name)
        icon = self._icon_from_source(icon_source) if icon_source else None
        self._icon_cache[cache_key] = icon
        return icon

    def _resolve_icon_source(self, process_name: str) -> str | None:
        shortcut_icon = self._desktop_shortcut_icon_path(process_name)
        if shortcut_icon:
            return shortcut_icon

        png_path = self._icon_png_path(process_name.lower())
        if png_path:
            return png_path

        return self._find_exe_path(process_name)

    def _icon_from_source(self, icon_source: str) -> QIcon:
        ext = os.path.splitext(icon_source)[1].lower()
        if ext in {".ico", ".png", ".jpg", ".jpeg"}:
            return QIcon(icon_source)
        return self._icon_provider.icon(QFileInfo(icon_source))

    @staticmethod
    def _icon_png_path(process_name_lower: str) -> str | None:
        p = os.path.join(get_app_root(), "assets", "icons", f"{process_name_lower}.png")
        return p if os.path.isfile(p) else None

    @staticmethod
    def _desktop_shortcut_icon_path(process_name: str) -> str | None:
        if os.name != "nt":
            return None
        try:
            import win32com.client
        except Exception:
            return None

        wanted = process_name.lower()
        desktop_dirs = []
        for env_name in ("USERPROFILE", "PUBLIC"):
            base = os.environ.get(env_name)
            if not base:
                continue
            desktop = os.path.join(base, "Desktop")
            if os.path.isdir(desktop):
                desktop_dirs.append(desktop)

        shell = win32com.client.Dispatch("WScript.Shell")
        for desktop in desktop_dirs:
            for name in os.listdir(desktop):
                if not name.lower().endswith(".lnk"):
                    continue
                shortcut_path = os.path.join(desktop, name)
                try:
                    shortcut = shell.CreateShortcut(shortcut_path)
                    target_path = shortcut.TargetPath or ""
                    if os.path.basename(target_path).lower() != wanted:
                        continue
                    icon_path = TodayOverviewPage._parse_icon_location(shortcut.IconLocation or "")
                    if icon_path and os.path.exists(icon_path):
                        return icon_path
                    if target_path and os.path.exists(target_path):
                        return target_path
                except Exception:
                    continue
        return None

    @staticmethod
    def _parse_icon_location(icon_location: str) -> str:
        icon_location = (icon_location or "").strip().strip('"')
        if not icon_location:
            return ""
        if "," not in icon_location:
            return icon_location
        path_part, index_part = icon_location.rsplit(",", 1)
        return path_part.strip().strip('"') if index_part.strip().lstrip("-").isdigit() else icon_location

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

    def _build_trend_data(self, sessions: list[dict]) -> tuple[list[int], list[int], list[int], list[int]]:
        today_series = self._build_hourly_series(sessions)

        yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_sessions = database.query_today_sessions(self.db_path, yesterday_str)
        yesterday_series = self._build_hourly_series(yesterday_sessions)

        # ── 7d / 30d: daily aggregation from DB
        today_date = date.today()
        seven_days = [(today_date - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(6, -1, -1)]
        thirty_days = [(today_date - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(29, -1, -1)]
        seven_day_stats = database.query_date_range_stats(self.db_path, seven_days)
        thirty_day_stats = database.query_date_range_stats(self.db_path, thirty_days)
        seven_day_series = [
            round((item.get("effective_seconds", 0) or 0) / 3600.0, 1)
            for item in seven_day_stats.get("daily", [])
        ]
        thirty_day_series = [
            round((item.get("effective_seconds", 0) or 0) / 3600.0, 1)
            for item in thirty_day_stats.get("daily", [])
        ]
        return today_series, yesterday_series, seven_day_series, thirty_day_series

    def _build_hourly_series(self, sessions: list[dict]) -> list[int]:
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
        return [int(round(v)) for v in hour_minutes]

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

    def _category_stats(self, stats: dict) -> tuple[int, int, int, int]:
        work_keys = {"ai_tools", "coding", "reading", "creative"}
        work_seconds = 0
        social_seconds = 0
        entertainment_seconds = 0
        tools_seconds = 0
        for item in stats.get("by_category", []):
            seconds = item.get("effective_seconds", 0) or 0
            category_key = item.get("category_key")
            if category_key in work_keys:
                work_seconds += seconds
            elif category_key == "social":
                social_seconds += seconds
            elif category_key == "video":
                entertainment_seconds += seconds
            elif category_key == "tools":
                tools_seconds += seconds
        return work_seconds, social_seconds, entertainment_seconds, tools_seconds

    def _color_for_category(self, category_key: str) -> str:
        if category_key in {"ai_tools", "coding", "reading", "creative"}:
            return ui_style.COLORS["coding_green"]
        if category_key == "video":
            return ui_style.COLORS["video_orange"]
        if category_key == "social":
            return ui_style.COLORS["social_purple"]
        if category_key in {"idle", "idle_leave"}:
            return ui_style.COLORS["idle_gray"]
        return ui_style.COLORS["ai_blue"]

    def _resolve_display(self, process_name: str, app_details: list[dict]) -> str:
        wrapper_processes = {"WindowsTerminal.exe", "cmd.exe", "powershell.exe", "Code.exe", "Cursor.exe"}

        # Wrapper processes: resolve actual app from window title first
        if process_name in wrapper_processes:
            top_title = ""
            top_seconds = 0
            for detail in app_details:
                if detail.get("process_name") != process_name:
                    continue
                seconds = detail.get("effective_seconds", 0) or 0
                if seconds > top_seconds:
                    top_seconds = seconds
                    top_title = detail.get("window_title", "") or ""

            for keyword, label in [
                ("Claude Code", "Claude Code"),
                ("Codex", "Codex"),
                ("Cursor", "Cursor"),
            ]:
                if keyword.lower() in top_title.lower():
                    return label
            # Fallback: use display mapping or process name
            return self.display_name_mapping.get(process_name) or process_name

        # Non-wrapper: use static display name mapping
        mapped_name = self.display_name_mapping.get(process_name)
        if mapped_name and mapped_name != process_name:
            return mapped_name
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
            work_seconds, social_seconds, entertainment_seconds, tools_seconds = self._category_stats(stats)
            result.append(
                {
                    "total": effective + idle_seconds,
                    "work": work_seconds,
                    "ent": entertainment_seconds,
                    "social": social_seconds,
                    "tools": tools_seconds,
                }
            )
        return result

    def _update_metrics(
        self,
        total_seconds: int,
        work_seconds: int,
        entertainment_seconds: int,
        social_seconds: int,
        tools_seconds: int,
        history: list[dict],
    ) -> None:
        values = {
            "total": total_seconds,
            "work": work_seconds,
            "ent": entertainment_seconds,
            "social": social_seconds,
            "tools": tools_seconds,
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
