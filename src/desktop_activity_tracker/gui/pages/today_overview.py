"""Dashboard home page."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ... import database, timeline
from ...database import count_consecutive_days, query_today_sessions
from ...exporter import _calculate_efficiency_score, _generate_suggestions
from ...utils import fmt_seconds
from ..style import COLORS, DASHBOARD_CARD_STYLE, SUBTLE_TAG_STYLE
from ..widgets.dashboard_widgets import (
    DistributionLegend,
    DonutChartWidget,
    MetricCard,
    ScoreGaugeWidget,
    TopAppListWidget,
    TimelineWidget,
)


class TodayOverviewPage(QWidget):
    """Modern dashboard page for today's activity overview."""

    def __init__(self, db_path, display_name_mapping=None):
        super().__init__()
        self.db_path = db_path
        self.display_name_mapping = display_name_mapping or {}
        self.metric_cards: dict[str, MetricCard] = {}
        self.focus_rows: list[QWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        self.warning_banner = QLabel()
        self.warning_banner.setWordWrap(True)
        self.warning_banner.setVisible(False)
        self.warning_banner.setStyleSheet(
            f"""
            QLabel {{
                font-size: 13px;
                font-weight: 700;
                color: white;
                background: #3A1620;
                border: 1px solid {COLORS['danger_red']};
                border-radius: 10px;
                padding: 10px 16px;
            }}
            """
        )
        root.addWidget(self.warning_banner)

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(10)
        metrics_grid.setVerticalSpacing(10)
        root.addLayout(metrics_grid)

        metric_specs = [
            ("total", "总使用时长", "🕘", COLORS["primary"]),
            ("work", "学习/工作时长", "📚", COLORS["coding_green"]),
            ("ent", "娱乐时长", "🎮", COLORS["video_orange"]),
            ("social", "社交通讯时长", "💬", COLORS["social_purple"]),
            ("idle", "挂机时长", "☕", COLORS["idle_gray"]),
        ]
        for col, (key, title, icon, color) in enumerate(metric_specs):
            card = MetricCard(title, icon, color)
            self.metric_cards[key] = card
            metrics_grid.addWidget(card, 0, col)

        middle_grid = QGridLayout()
        middle_grid.setHorizontalSpacing(10)
        middle_grid.setVerticalSpacing(10)
        root.addLayout(middle_grid)

        middle_grid.addWidget(self._build_distribution_card(), 0, 0, 1, 5)
        middle_grid.addWidget(self._build_score_card(), 0, 5, 1, 3)
        middle_grid.addWidget(self._build_focus_card(), 0, 8, 1, 3)

        bottom_grid = QGridLayout()
        bottom_grid.setHorizontalSpacing(10)
        bottom_grid.setVerticalSpacing(10)
        root.addLayout(bottom_grid, 1)

        bottom_grid.addWidget(self._build_trend_card(), 0, 0, 1, 6)
        self.top_app_card = TopAppListWidget()
        bottom_grid.addWidget(self.top_app_card, 0, 6, 1, 5)

        for col in range(11):
            weight = 1
            if col in (0, 1, 2, 3, 4):
                weight = 2
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
        layout.setSpacing(8)

        title = QLabel("时间分布")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.donut_widget = DonutChartWidget()
        row.addWidget(self.donut_widget, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        self.legend_widget = DistributionLegend()
        right.addWidget(self.legend_widget, 1)

        self.active_ratio_label = QLabel("有效时间占比：--")
        self.active_ratio_label.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {COLORS['primary']};"
        )
        right.addWidget(self.active_ratio_label)
        row.addLayout(right, 1)

        layout.addLayout(row)
        return card

    def _build_score_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(DASHBOARD_CARD_STYLE)
        card.setFixedHeight(235)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        title = QLabel("效率评分")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        layout.addWidget(title)

        self.score_gauge = ScoreGaugeWidget()
        layout.addWidget(self.score_gauge, 1)

        self.score_grade = QLabel("数据不足")
        self.score_grade.setAlignment(Qt.AlignCenter)
        self.score_grade.setMaximumHeight(24)
        self.score_grade.setStyleSheet(SUBTLE_TAG_STYLE)
        layout.addWidget(self.score_grade, 0)

        self.score_detail = QLabel("活跃数据不足 30 分钟，暂不评分。")
        self.score_detail.setWordWrap(True)
        self.score_detail.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
        self.score_detail.setMaximumHeight(32)
        layout.addWidget(self.score_detail)
        return card

    def _build_focus_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(DASHBOARD_CARD_STYLE)
        card.setFixedHeight(235)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("今日专注")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        header.addWidget(title)
        header.addStretch()
        self.consecutive_label = QLabel("")
        self.consecutive_label.setStyleSheet(
            f"font-size: 11px; color: {COLORS['primary']}; font-weight: 700;"
        )
        header.addWidget(self.consecutive_label)
        layout.addLayout(header)

        self.longest_focus_label = QLabel("")
        self.longest_focus_label.setWordWrap(True)
        self.longest_focus_label.setVisible(False)
        self.longest_focus_label.setStyleSheet(
            f"""
            QLabel {{
                font-size: 12px; font-weight: 700;
                color: {COLORS['coding_green']};
                background: {COLORS['panel_bg_alt']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 8px;
                padding: 6px 10px;
            }}
            """
        )
        layout.addWidget(self.longest_focus_label)

        self.focus_container = QVBoxLayout()
        self.focus_container.setSpacing(6)
        layout.addLayout(self.focus_container)
        layout.addStretch()
        return card

    def _build_trend_card(self):
        self.timeline_widget = TimelineWidget()
        return self.timeline_widget

    def refresh(self):
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            totals = stats.get("totals", {})
            effective = totals.get("effective_seconds", 0) or 0
            idle_sec = totals.get("idle_seconds", 0) or 0
            total_sec = effective + idle_sec

            work_keys = {"ai_tools", "coding", "reading", "creative"}
            work_sec = 0
            social_sec = 0
            ent_sec = 0
            for item in stats.get("by_category", []):
                seconds = item.get("effective_seconds", 0) or 0
                key = item.get("category_key")
                if key in work_keys:
                    work_sec += seconds
                elif key == "social":
                    social_sec += seconds
                elif key in {"video", "gaming"}:
                    ent_sec += seconds

            history = self._load_metric_history(8)
            self._update_metrics(total_sec, work_sec, ent_sec, social_sec, idle_sec, history)

            # Entertainment warning
            if ent_sec > 5400:
                ent_min = int(ent_sec // 60)
                self.warning_banner.setText(
                    f"⚠ 今日娱乐时间已达 {ent_min} 分钟（超过90分钟），建议控制娱乐活动。"
                )
                self.warning_banner.setVisible(True)
            else:
                self.warning_banner.setVisible(False)

            other_sec = max(effective - work_sec - social_sec - ent_sec, 0)
            distribution = [
                ("学习/工作", work_sec, COLORS["coding_green"]),
                ("娱乐", ent_sec, COLORS["video_orange"]),
                ("社交通讯", social_sec, COLORS["social_purple"]),
                ("挂机", idle_sec, COLORS["idle_gray"]),
                ("其他", other_sec, "#C0CADB"),
            ]
            self.donut_widget.set_data(total_sec, distribution)
            self.legend_widget.set_items(distribution, total_sec)
            active_ratio = int(round((effective / total_sec) * 100)) if total_sec else 0
            self.active_ratio_label.setText(f"有效时间占比：{active_ratio}%")

            self._update_score_card(work_sec, ent_sec, effective, stats, today)

            # Session-based timeline
            sessions = query_today_sessions(self.db_path, today)
            self.timeline_widget.set_sessions(sessions, self.display_name_mapping)

            # Focus blocks (still uses 30-min aggregation for detection)
            tl = timeline.build_timeline(self.db_path, today)
            focus_blocks = timeline.identify_focus_blocks(tl)
            self._update_focus_blocks(focus_blocks)

            # Consecutive days
            cons = count_consecutive_days(self.db_path)
            if cons >= 3:
                self.consecutive_label.setText(f"🔥 连续 {cons} 天")
                self.consecutive_label.setVisible(True)
            elif cons >= 1:
                self.consecutive_label.setText(f"第 {cons} 天")
                self.consecutive_label.setVisible(True)
            else:
                self.consecutive_label.setVisible(False)

            # Merge by resolved display name, then take top 5
            merged: dict[str, int] = {}
            for item in stats.get("by_app", []):
                pname = item.get("process_name") or "Unknown"
                display = self._resolve_display(pname, stats.get("by_app_detail", []))
                secs = item.get("effective_seconds", 0) or 0
                merged[display] = merged.get(display, 0) + secs
            sorted_apps = sorted(merged.items(), key=lambda x: -x[1])[:5]
            top_apps = [(name, name, secs) for name, secs in sorted_apps]
            self.top_app_card.set_items(top_apps)
        except Exception:
            import traceback

            traceback.print_exc()

    def _resolve_display(self, process_name, app_details):
        """Resolve a display name using mapping + window title heuristics.

        For wrapper processes (terminal, cmd, etc.), check if the most-used
        window title reveals the actual tool being used (e.g. Claude Code).
        """
        pname = process_name or ""
        # Normalize Python variants to a single label
        import re
        if re.match(r'^python\d*w?\.exe$', pname, re.IGNORECASE):
            return "Python"
        # Check explicit mapping first
        mapped = self.display_name_mapping.get(pname)
        if mapped and mapped != pname:
            return mapped

        # Wrapper processes — try to identify the actual tool from titles
        WRAPPER_PROCS = {
            "WindowsTerminal.exe", "cmd.exe", "powershell.exe",
            "Code.exe", "Cursor.exe",
        }
        if pname not in WRAPPER_PROCS:
            return mapped or pname

        # Find the top window title for this process
        best_title = ""
        best_sec = 0
        for d in app_details:
            if d.get("process_name") == pname:
                sec = d.get("effective_seconds", 0) or 0
                if sec > best_sec:
                    best_sec = sec
                    best_title = d.get("window_title", "") or ""

        if not best_title:
            return mapped or pname

        # Known tool patterns in window titles
        TOOL_PATTERNS = [
            ("Claude Code", "Claude Code"),
            ("Codex", "Codex"),
            ("Cursor", "Cursor"),
            ("Trae", "Trae"),
            ("GitHub", "GitHub"),
            ("GitLab", "GitLab"),
            ("Docker", "Docker"),
        ]
        for pattern, label in TOOL_PATTERNS:
            if pattern.lower() in best_title.lower():
                return label

        return mapped or pname

    def _load_metric_history(self, days: int):
        today = datetime.now().date()
        dates = [today - timedelta(days=idx) for idx in range(days - 1, -1, -1)]
        history = []
        work_keys = {"ai_tools", "coding", "reading", "creative"}
        for dt in dates:
            date_str = dt.strftime("%Y-%m-%d")
            day_stats = database.query_date_stats(self.db_path, date_str)
            totals = day_stats.get("totals", {})
            effective = totals.get("effective_seconds", 0) or 0
            idle_sec = totals.get("idle_seconds", 0) or 0
            work_sec = 0
            social_sec = 0
            ent_sec = 0
            for item in day_stats.get("by_category", []):
                seconds = item.get("effective_seconds", 0) or 0
                key = item.get("category_key")
                if key in work_keys:
                    work_sec += seconds
                elif key == "social":
                    social_sec += seconds
                elif key in {"video", "gaming"}:
                    ent_sec += seconds
            history.append(
                {
                    "total": effective + idle_sec,
                    "work": work_sec,
                    "ent": ent_sec,
                    "social": social_sec,
                    "idle": idle_sec,
                }
            )
        return history

    def _update_metrics(self, total_sec, work_sec, ent_sec, social_sec, idle_sec, history):
        mapping = {
            "total": total_sec,
            "work": work_sec,
            "ent": ent_sec,
            "social": social_sec,
            "idle": idle_sec,
        }

        for key, current in mapping.items():
            card = self.metric_cards[key]
            card.set_value(_compact_duration(current), self._delta_text(current, history, key))
            card.set_sparkline([day[key] for day in history])
        self.metric_cards["ent"].set_warning(ent_sec > 5400)

    def _delta_text(self, current: int, history: list[dict], key: str):
        if len(history) < 2:
            return "较昨日 --"
        yesterday = history[-2].get(key, 0) or 0
        diff = current - yesterday
        if diff == 0:
            return "较昨日 持平"
        arrow = "↑" if diff > 0 else "↓"
        return f"较昨日 {arrow} {_compact_duration(abs(diff))}"

    def _update_score_card(self, work_sec, ent_sec, effective, stats, today):
        score = _calculate_efficiency_score(work_sec, ent_sec, effective)
        if score is None:
            self.score_gauge.set_score(None, COLORS["idle_gray"])
            self.score_grade.setText("数据不足")
            self.score_grade.setStyleSheet(SUBTLE_TAG_STYLE)
            self.score_detail.setText("活跃数据不足 30 分钟，暂不评分。")
            return

        if score >= 80:
            grade = "优秀"
            accent = COLORS["coding_green"]
        elif score >= 60:
            grade = "良好"
            accent = COLORS["primary"]
        elif score >= 40:
            grade = "一般"
            accent = COLORS["warning_yellow"]
        else:
            grade = "需改进"
            accent = COLORS["danger_red"]

        if effective > 0:
            work_ratio = int(round(work_sec / effective * 100))
            ent_ratio = int(round(ent_sec / effective * 100))
        else:
            work_ratio = 0
            ent_ratio = 0

        suggestions, _, _ = _generate_suggestions(self.db_path, today, stats)
        if suggestions and ent_sec > 5400:
            hint = "建议控制娱乐时间"
        elif suggestions:
            s = suggestions[0]
            hint = s[:24] + "…" if len(s) > 24 else s
        else:
            hint = "继续保持"

        self.score_gauge.set_score(score, accent)
        self.score_grade.setText(f"{grade} · 学习占{work_ratio}% · 娱乐占{ent_ratio}%")
        self.score_grade.setStyleSheet(
            f"""
            QLabel {{
                font-size: 12px;
                font-weight: 700;
                color: white;
                background: {accent};
                border-radius: 12px;
                padding: 4px 10px;
            }}
            """
        )
        self.score_detail.setText(hint)

    def _update_focus_blocks(self, focus_blocks):
        while self.focus_rows:
            row = self.focus_rows.pop()
            self.focus_container.removeWidget(row)
            row.deleteLater()

        # Longest focus
        if focus_blocks:
            longest = max(focus_blocks, key=lambda f: f.duration_minutes)
            apps_display = []
            for app in longest.top_apps[:2]:
                apps_display.append(self.display_name_mapping.get(app, app))
            apps_text = " / ".join(apps_display) if apps_display else "未识别"
            self.longest_focus_label.setText(
                f"⚡ 最长专注 {longest.start_slot}-{longest.end_slot}  "
                f"{longest.duration_minutes}分钟 · {longest.main_category} · {apps_text}"
            )
            self.longest_focus_label.setVisible(True)
        else:
            self.longest_focus_label.setVisible(False)

        if not focus_blocks:
            placeholder = QLabel("今日暂未识别到连续专注时段。")
            placeholder.setStyleSheet(f"font-size: 13px; color: {COLORS['text_muted']};")
            self.focus_container.addWidget(placeholder)
            self.focus_rows.append(placeholder)
            return

        for focus in focus_blocks[:2]:
            row = QFrame()
            row.setStyleSheet(
                f"""
                QFrame {{
                    background: {COLORS['panel_bg_alt']};
                    border: 1px solid {COLORS['border_light']};
                    border-radius: 12px;
                }}
                """
            )
            line = QVBoxLayout(row)
            line.setContentsMargins(10, 8, 10, 8)
            line.setSpacing(4)

            head = QLabel(
                f"{focus.start_slot} - {focus.end_slot}    {focus.duration_minutes}分钟"
            )
            head.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {COLORS['text']};")
            line.addWidget(head)

            apps_display = []
            for app in focus.top_apps[:3]:
                apps_display.append(self.display_name_mapping.get(app, app))
            apps = " / ".join(apps_display) if apps_display else "主应用未识别"
            sub = QLabel(f"{focus.main_category} · {apps}")
            sub.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
            line.addWidget(sub)

            self.focus_container.addWidget(row)
            self.focus_rows.append(row)


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
