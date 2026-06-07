"""Dashboard home page."""

from __future__ import annotations

import os
import time
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

from ... import get_app_root
from ...services.dashboard_service import load_today_snapshot
from ...utils import normalize_category_display_name
from .. import style as ui_style
from ..widgets.dashboard_widgets import (
    ActiveRatioRingWidget,
    DistributionLegend,
    DonutChartWidget,
    FocusTimelineBarWidget,
    SessionTop3Widget,
    TimelineWidget,
    TopAppListWidget,
    TrendChartWidget,
)


class TodayOverviewPage(QWidget):
    def __init__(self, db_path, display_name_mapping=None):
        super().__init__()
        self.db_path = db_path
        self.display_name_mapping = display_name_mapping or {}
        self.last_stats_date: str | None = None
        self.last_stats: dict[str, object] = {}
        self.last_snapshot_totals: dict[str, object] = {}
        self.last_consecutive_days = 0
        setattr(self, "metric_cards", {})
        self.time_stats_labels: dict[str, QLabel] = {}
        self.distribution_cmp_labels: dict[str, QLabel] = {}
        self._icon_provider = QFileIconProvider()
        self._icon_cache: dict[str, QIcon | None] = {}
        self._is_active = False
        self._refresh_scheduled = False
        self._last_refresh_at = 0.0
        self._refresh_interval_seconds = 5.0

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        content_grid = QGridLayout()
        content_grid.setHorizontalSpacing(14)
        content_grid.setVerticalSpacing(14)
        root.addLayout(content_grid, 1)

        self.distribution_card = self._build_distribution_card()
        self.focus_timeline_card = self._build_focus_timeline_card()
        self.time_stats_card = None
        self.time_stats_ratio_ring = None
        content_grid.addWidget(self.distribution_card, 0, 0, 1, 8)
        self.trend_card = TrendChartWidget()
        content_grid.addWidget(self.trend_card, 0, 8, 1, 4)
        content_grid.addWidget(self.focus_timeline_card, 1, 0, 1, 8)
        self.top_app_card = TopAppListWidget()
        content_grid.addWidget(self.top_app_card, 1, 8, 1, 4)

        content_grid.setRowStretch(0, 4)
        content_grid.setRowStretch(1, 6)
        for column in range(12):
            content_grid.setColumnStretch(column, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_if_active)
        self.timer.setInterval(5000)
        self.insight_card = None
        self.insight_grid_widget = None
        self.insight_empty_label = None

    def activate(self, force: bool = False) -> None:
        self._is_active = True
        if not self.timer.isActive():
            self.timer.start()
        if force or self._needs_refresh():
            self.schedule_refresh(force=force)

    def deactivate(self) -> None:
        self._is_active = False
        self._refresh_scheduled = False
        self.timer.stop()

    def schedule_refresh(self, force: bool = False) -> None:
        if self._refresh_scheduled:
            return
        self._refresh_scheduled = True
        QTimer.singleShot(0, lambda: self._run_scheduled_refresh(force))

    def _run_scheduled_refresh(self, force: bool) -> None:
        self._refresh_scheduled = False
        if not self._is_active and not force:
            return
        if force or self._needs_refresh():
            self.refresh()

    def _needs_refresh(self) -> bool:
        return (time.time() - self._last_refresh_at) >= self._refresh_interval_seconds

    def _refresh_if_active(self) -> None:
        if self._is_active:
            self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.activate(force=False)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.deactivate()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.deactivate()
        super().closeEvent(event)

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
        card.setMinimumHeight(282)

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

        cmp_row = QHBoxLayout()
        cmp_row.setSpacing(8)
        cmp_title = QLabel("较昨日")
        cmp_title.setStyleSheet(
            f"font-size: 14px; color: {ui_style.COLORS['text_secondary']}; font-weight: 700;"
        )
        cmp_row.addWidget(cmp_title)

        self.distribution_cmp_labels = {}
        for key, icon, label_text, color in [
            ("work", "💼", "工作学习", ui_style.COLORS["coding_green"]),
            ("entertainment", "📺", "娱乐休闲", ui_style.COLORS["video_orange"]),
            ("social", "💬", "社交通讯", ui_style.COLORS["social_purple"]),
        ]:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet(f"font-size: 14px; color: {color};")
            cmp_row.addWidget(icon_label)

            name_label = QLabel(label_text)
            name_label.setStyleSheet(
                f"font-size: 13px; color: {ui_style.COLORS['text_secondary']}; font-weight: 700;"
            )
            cmp_row.addWidget(name_label)

            value_label = QLabel("--")
            value_label.setStyleSheet(
                f"font-size: 13px; color: {ui_style.COLORS['text']}; font-weight: 800;"
            )
            cmp_row.addWidget(value_label)
            self.distribution_cmp_labels[key] = value_label

        cmp_row.addStretch()
        layout.addLayout(cmp_row)
        return card

    def _build_time_stats_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(ui_style.get_dashboard_card_style())
        card.setMinimumHeight(270)

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
            ("work", "💼", "工作学习"),
            ("entertainment", "📺", "娱乐休闲"),
            ("social", "💬", "社交通讯"),
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
        layout.setContentsMargins(14, 5, 14, 4)
        layout.setSpacing(2)

        title = QLabel("今日专注时间轴")
        title.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {ui_style.COLORS['text']};")
        layout.addWidget(title)

        self.focus_axis = FocusTimelineBarWidget()
        layout.addWidget(self.focus_axis)

        tick_row = QHBoxLayout()
        tick_row.setSpacing(0)
        for index, text in enumerate(["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"]):
            label = QLabel(text)
            label.setStyleSheet(f"font-size: 9px; color: {ui_style.COLORS['text_muted']};")
            tick_row.addWidget(label)
            if index < 6:
                tick_row.addStretch()
        layout.addLayout(tick_row)

        legend_row = QHBoxLayout()
        legend_row.setSpacing(0)
        for name, color in [
            ("💼 工作学习", ui_style.COLORS["coding_green"]),
            ("📺 娱乐休闲", ui_style.COLORS["video_orange"]),
            ("💬 社交通讯", ui_style.COLORS["social_purple"]),
            ("📦 其他", ui_style.get_category_color("other")),
            ("💤 离开/空闲", ui_style.COLORS["timeline_idle"]),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size: 10px; color: {color};")
            text_label = QLabel(name)
            text_label.setStyleSheet(f"font-size: 10px; color: {ui_style.COLORS['text_secondary']};")
            legend_row.addWidget(dot)
            legend_row.addWidget(text_label)
            legend_row.addSpacing(6)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        self.focus_hint = QLabel("今日暂未识别到连续专注时段。")
        self.focus_hint.setStyleSheet(f"font-size: 10px; color: {ui_style.COLORS['text_secondary']};")
        layout.addWidget(self.focus_hint)

        self.consecutive_label = QLabel("")
        self.consecutive_label.setVisible(False)

        section_title = QLabel("今日关键 Session")
        section_title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {ui_style.COLORS['text']};")
        layout.addWidget(section_title)

        self.session_top3_widget = SessionTop3Widget()
        layout.addWidget(self.session_top3_widget, 1)
        return card

    def refresh(self) -> None:
        snapshot = load_today_snapshot(self.db_path, self._resolve_display)
        self._last_refresh_at = time.time()
        self.last_stats_date = str(snapshot["today"])
        self.last_stats = dict(snapshot["stats"])
        totals = snapshot["totals"]
        self.last_snapshot_totals = dict(totals)
        effective = int(totals["effective_seconds"])
        idle_seconds = int(totals["idle_seconds"])
        active_ratio = int(totals["active_ratio"])

        distribution = [
            (str(item["label"]), int(item["seconds"]), self._distribution_color(str(item["category_key"])))
            for item in snapshot["distribution_sections"]
        ]
        self.donut_widget.set_data(effective, distribution)
        self.legend_widget.set_items(distribution, effective)

        self.active_status_label.setText(f"活跃占比 {active_ratio}%")
        self.idle_status_label.setText(f"挂机/空闲 {_compact_duration(idle_seconds)}")

        for key, label in self.distribution_cmp_labels.items():
            item = snapshot["day_comparison"].get(key, {})
            direction = str(item.get("direction", "empty"))
            delta = int(item.get("delta_seconds", 0) or 0)
            if direction == "empty":
                label.setText("--")
                label.setStyleSheet(
                    f"font-size: 13px; color: {ui_style.COLORS['text_muted']}; font-weight: 800;"
                )
            elif direction == "flat":
                label.setText("≈ 0")
                label.setStyleSheet(
                    f"font-size: 13px; color: {ui_style.COLORS['text_muted']}; font-weight: 800;"
                )
            elif direction == "up":
                label.setText(f"+{_compact_duration(delta)}")
                label.setStyleSheet(
                    f"font-size: 13px; color: {ui_style.COLORS['success_green']}; font-weight: 800;"
                )
            else:
                label.setText(f"-{_compact_duration(abs(delta))}")
                label.setStyleSheet(
                    f"font-size: 13px; color: {ui_style.COLORS['danger_red']}; font-weight: 800;"
                )

        sessions = [
            {
                **session,
                "category_name": normalize_category_display_name(
                    str(session.get("category_key", "") or ""),
                    str(session.get("category_name", "") or ""),
                ),
            }
            for session in snapshot["sessions"]
        ]
        sessions_with_icons = []
        for session in sessions:
            proc = str(session.get("process_name", ""))
            sessions_with_icons.append({**session, "_icon": self._app_icon(proc)})
        timeline_sessions = sorted(
            sessions,
            key=lambda session: (
                str(session.get("start_time", "") or ""),
                str(session.get("end_time", "") or ""),
            ),
        )
        self.session_top3_widget.set_sessions(sessions_with_icons, self.display_name_mapping)
        self.focus_axis.set_minutes(self._build_focus_axis(timeline_sessions))
        trend = snapshot["trend"]
        self.trend_card.set_data(
            trend["today"],
            trend["yesterday"],
            trend["seven_days"],
            trend["thirty_days"],
            work_today=trend.get("today_work", []),
            entertainment_today=trend.get("today_entertainment", []),
        )
        focus_summary = str(snapshot["focus_summary"])
        self.focus_hint.setText(focus_summary)
        self.focus_hint.setVisible("暂未识别" not in focus_summary)
        consecutive_days = int(snapshot["consecutive_days"])
        self.last_consecutive_days = consecutive_days
        self.consecutive_label.setText(f"连续专注 {consecutive_days}天" if consecutive_days > 0 else "")
        self._update_top_apps(snapshot["top_app_rows"])

    def _update_top_apps(self, rows_data: list[dict[str, object]]) -> None:
        rows = []
        for item in rows_data:
            process_name = str(item["process_name"])
            display_name = str(item["display_name"])
            seconds = int(item["seconds"])
            icon_process = self._icon_process_for_display(process_name, display_name)
            rows.append((process_name, display_name, seconds, self._app_icon(icon_process)))
        self.top_app_card.set_items(rows)

    def _distribution_color(self, category_key: str) -> str:
        return {
            "work": ui_style.COLORS["coding_green"],
            "video": ui_style.COLORS["video_orange"],
            "social": ui_style.COLORS["social_purple"],
            "other": ui_style.get_category_color("other"),
        }.get(category_key, ui_style.get_category_color("other"))

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
        colors = [ui_style.COLORS["timeline_idle"]] * 1440
        for session in sessions:
            start = self._to_minute(session.get("start_time", ""))
            end = max(start, self._to_minute(session.get("end_time", "")))
            color = self._color_for_category(session.get("category_key") or "other", str(session.get("category_name", "") or ""))
            for minute in range(max(0, start), min(1439, end) + 1):
                colors[minute] = color
        return colors

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

    def _color_for_category(self, category_key: str, category_name: str = "") -> str:
        if category_key in {"ai_tools", "coding", "reading", "creative"}:
            return ui_style.COLORS["coding_green"]
        if category_key == "video":
            return ui_style.COLORS["video_orange"]
        if category_key == "social":
            return ui_style.COLORS["social_purple"]
        if category_key in {"idle", "idle_leave", "hangup"}:
            return ui_style.COLORS["timeline_idle"]
        if category_name in {"空闲", "挂机", "离开"}:
            return ui_style.COLORS["timeline_idle"]
        return ui_style.get_category_color("other")

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
