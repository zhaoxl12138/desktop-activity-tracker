"""Reusable widgets for the dashboard home page."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...utils import fmt_seconds
from .. import style as ui_style
from ..style import COLORS, get_category_color


class DonutChartWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._total_seconds = 0
        self._segments: list[tuple[str, int, str]] = []
        self.setMinimumSize(150, 150)

    def set_data(self, total_seconds: int, segments: list[tuple[str, int, str]]) -> None:
        self._total_seconds = max(0, int(total_seconds or 0))
        self._segments = segments
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = max(100, min(self.width(), self.height()) - 24)
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        ring_width = min(24.0, max(20.0, side * 0.14))

        base_pen = QPen(QColor(COLORS["border"]), ring_width)
        base_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(base_pen)
        painter.drawArc(rect, 0, 360 * 16)

        if self._total_seconds <= 0:
            painter.setPen(QColor(COLORS["text_muted"]))
            font = painter.font()
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "暂无数据")
            return

        start_angle = 90 * 16
        for _, seconds, color in self._segments:
            if seconds <= 0:
                continue
            span = int((seconds / self._total_seconds) * 360 * 16)
            pen = QPen(QColor(color), ring_width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, -start_angle, -span)
            start_angle += span

        # Center text: active duration
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text_muted"]))
        painter.drawText(QRectF(rect.left(), rect.center().y() - 18, rect.width(), 16),
                         Qt.AlignCenter, "活跃时长")

        font.setPixelSize(17)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(QRectF(rect.left(), rect.center().y(), rect.width(), 22),
                         Qt.AlignCenter, fmt_seconds(self._total_seconds))


class ActiveRatioRingWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._ratio = 0
        self.setMinimumSize(170, 170)

    def set_ratio(self, ratio: int) -> None:
        self._ratio = max(0, min(100, int(ratio or 0)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height()) - 22
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        ring_width = 12

        base_pen = QPen(QColor(COLORS["panel_bg_alt"]), ring_width)
        base_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(base_pen)
        painter.drawArc(rect, 0, 360 * 16)

        value_pen = QPen(QColor(COLORS["success_green"]), ring_width)
        value_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(value_pen)
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * self._ratio / 100))

        font = painter.font()
        font.setPixelSize(34)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(QRectF(rect.left(), rect.center().y() - 30, rect.width(), 42), Qt.AlignCenter, f"{self._ratio}%")

        font.setPixelSize(13)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text_secondary"]))
        painter.drawText(QRectF(rect.left(), rect.center().y() + 12, rect.width(), 24), Qt.AlignCenter, "活跃时间占比")


class FocusTimelineBarWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._minute_colors = [COLORS["timeline_idle"]] * 1440
        self.setFixedHeight(24)

    def set_minutes(self, minute_colors: list[str]) -> None:
        if len(minute_colors) == 1440:
            self._minute_colors = minute_colors
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(2, 5, -2, -5)
        minute_width = rect.width() / 1440.0
        start_index = 0
        current_color = self._minute_colors[0]

        for index in range(1, 1440):
            if self._minute_colors[index] == current_color:
                continue
            left = rect.left() + start_index * minute_width
            right = rect.left() + index * minute_width
            painter.fillRect(
                QRectF(left, rect.top(), max(1.0, right - left), rect.height()),
                QColor(current_color),
            )
            start_index = index
            current_color = self._minute_colors[index]

        left = rect.left() + start_index * minute_width
        painter.fillRect(
            QRectF(left, rect.top(), max(1.0, rect.right() - left + 1), rect.height()),
            QColor(current_color),
        )
        painter.setPen(QPen(QColor(COLORS["border_light"]), 1))
        painter.drawRoundedRect(rect, 6, 6)


class TimelineWidget(QFrame):
    CATEGORY_COLORS = {
        "办公": COLORS["coding_green"],
        "工作学习": COLORS["coding_green"],
        "视频娱乐": COLORS["video_orange"],
        "娱乐休闲": COLORS["video_orange"],
        "社交通讯": COLORS["social_purple"],
        "浏览器": COLORS["tools_grey"],
        "系统工具": COLORS["tools_grey"],
        "挂机": COLORS["idle_gray"],
        "离开": COLORS["idle_gray"],
        "空闲": COLORS["idle_gray"],
        "其他": COLORS["other_teal"],
    }

    def __init__(
        self,
        max_rows: int = 8,
        show_title: bool = True,
        open_detail_on_more: bool = False,
        min_effective_seconds: int = 0,
        sort_by_value: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._max_rows = max_rows
        self._show_title = show_title
        self._open_detail_on_more = open_detail_on_more
        self._min_effective_seconds = max(0, min_effective_seconds)
        self._sort_by_value = sort_by_value
        self._rows: list[QWidget] = []
        self._sessions: list[dict] = []
        self._display_name_mapping = {}
        self._expanded = True
        self._detail_dialog: QDialog | None = None
        self.setObjectName("dashboardCard")
        self.setStyleSheet("QFrame#dashboardCard { background: transparent; border: none; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        if self._show_title:
            title = QLabel("今日时间线")
            title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
            root.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(
            f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 2px 0 2px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {COLORS['border_light']};
                border-radius: 4px;
                min-height: 36px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLORS['primary']};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
                height: 0;
            }}
            """
        )

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 2, 0)
        self._content_layout.setSpacing(2)
        self._content_layout.addStretch()
        self.scroll.setWidget(self._content)
        root.addWidget(self.scroll, 1)

        self.more_label = QPushButton("查看更多 ↓")
        self.more_label.setCursor(Qt.PointingHandCursor)
        self.more_label.setFlat(True)
        self.more_label.setStyleSheet(
            f"""
            QPushButton {{
                font-size: 14px;
                color: {COLORS['primary']};
                font-weight: 700;
                border: none;
                background: transparent;
                padding: 0;
            }}
            QPushButton:hover {{
                color: {COLORS['primary_hover']};
            }}
            """
        )
        self.more_label.clicked.connect(self.toggle_expanded)
        root.addWidget(self.more_label, 0, Qt.AlignHCenter)

    def set_sessions(self, sessions, display_name_mapping=None) -> None:
        merged_sessions = self._merge_sessions(list(sessions or []))
        filtered_sessions = [session for session in merged_sessions if self._should_show_session(session)]
        if self._sort_by_value:
            filtered_sessions.sort(
                key=lambda session: (
                    -self._session_effective_seconds(session),
                    str(session.get("end_time", "") or ""),
                )
            )
        self._sessions = filtered_sessions
        self._display_name_mapping = display_name_mapping or {}
        self._expanded = len(self._sessions) > self._max_rows
        self._render_rows()

    def _merge_sessions(self, sessions: list[dict]) -> list[dict]:
        if len(sessions) <= 1:
            return sessions
        merged = []
        current = dict(sessions[0])
        for next_sess in sessions[1:]:
            same_window = (
                current.get("process_name") == next_sess.get("process_name")
                and current.get("category_key") == next_sess.get("category_key")
                and current.get("normalized_title") == next_sess.get("normalized_title")
            )
            adjacent = False
            if same_window:
                try:
                    curr_end = datetime.strptime(current.get("end_time", ""), "%Y-%m-%d %H:%M:%S")
                    next_start = datetime.strptime(next_sess.get("start_time", ""), "%Y-%m-%d %H:%M:%S")
                    adjacent = (next_start - curr_end).total_seconds() <= 60
                except Exception:
                    pass
            if same_window and adjacent:
                current["end_time"] = next_sess.get("end_time", current.get("end_time"))
                current["effective_seconds"] = (current.get("effective_seconds", 0) or 0) + (next_sess.get("effective_seconds", 0) or 0)
                current["duration_seconds"] = (current.get("duration_seconds", 0) or 0) + (next_sess.get("duration_seconds", 0) or 0)
                current["idle_seconds"] = (current.get("idle_seconds", 0) or 0) + (next_sess.get("idle_seconds", 0) or 0)
            else:
                merged.append(current)
                current = dict(next_sess)
        merged.append(current)
        return merged

    def _should_show_session(self, session: dict) -> bool:
        if self._min_effective_seconds <= 0:
            return True
        return self._session_effective_seconds(session) >= self._min_effective_seconds

    @staticmethod
    def _session_effective_seconds(session: dict) -> int:
        effective = session.get("effective_seconds", 0) or 0
        if effective:
            return int(effective)
        duration = session.get("duration_seconds", 0) or 0
        return int(duration)

    def _session_display_label(self, session: dict) -> str:
        process_name = str(session.get("process_name", "") or "")
        base_name = self._display_name_mapping.get(process_name, process_name) or process_name or "未知应用"
        title = str(session.get("normalized_title", "") or session.get("window_title", "") or "").strip()
        if not title:
            return base_name
        normalized_title = title.lower()
        normalized_base = base_name.lower()
        if normalized_title == normalized_base:
            return base_name
        if normalized_title in normalized_base or normalized_base in normalized_title:
            return base_name
        if normalized_title in {"program manager", "desktop", "start", "任务管理器"}:
            return base_name
        if len(title) > 20:
            title = title[:20] + "…"
        return f"{base_name}({title})"

    @staticmethod
    def _session_duration_text(session: dict) -> str:
        seconds = TimelineWidget._session_effective_seconds(session)
        if seconds < 60:
            return f"{seconds}秒"
        minutes = max(1, int(round(seconds / 60.0)))
        return f"{minutes}分钟"

    @staticmethod
    def _short_time_range(session: dict) -> str:
        start = str(session.get("start_time", "") or "")
        end = str(session.get("end_time", "") or "")
        start_short = start[-8:-3] if len(start) >= 8 else start
        end_short = end[-8:-3] if len(end) >= 8 else end
        if start_short == end_short:
            start_short = start[-8:] if len(start) >= 8 else start
            end_short = end[-8:] if len(end) >= 8 else end
        return f"{start_short} - {end_short}".strip()

    def _build_session_card(self, session: dict, color: str) -> QWidget:
        card = QFrame()
        card.setObjectName("sessionCard")
        card.setStyleSheet(
            f"""
            QFrame#sessionCard {{
                background: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 12px;
            }}
            """
        )

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        accent = QFrame()
        accent.setFixedWidth(4)
        accent.setStyleSheet(f"background: {color}; border-radius: 2px;")
        layout.addWidget(accent)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        app_label = QLabel(self._session_display_label(session))
        app_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text']}; font-weight: 800;")
        app_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_row.addWidget(app_label, 1)

        duration_label = QLabel(self._session_duration_text(session))
        duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        duration_label.setStyleSheet(f"font-size: 12px; color: {color}; font-weight: 800;")
        top_row.addWidget(duration_label, 0, Qt.AlignRight)

        body.addLayout(top_row)

        time_label = QLabel(self._short_time_range(session))
        time_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        time_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(time_label)

        category_name = str(session.get("category_name", "") or "其他")
        category_chip = QLabel(category_name)
        category_chip.setStyleSheet(
            f"""
            QLabel {{
                font-size: 10px;
                color: {color};
                font-weight: 800;
                padding: 2px 8px;
                border-radius: 999px;
                border: 1px solid {color};
                background: rgba(255, 255, 255, 0.03);
            }}
            """
        )
        body.addWidget(category_chip)

        layout.addLayout(body, 1)
        return card

    def toggle_expanded(self) -> None:
        if len(self._sessions) <= self._max_rows:
            return
        if self._open_detail_on_more:
            self.show_detail_dialog()
            return
        self._expanded = not self._expanded
        self._render_rows()

    def show_detail_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("今日专注 Session")
        dialog.setModal(True)
        dialog.resize(980, 720)
        dialog.setStyleSheet(
            f"""
            QDialog {{
                background: {COLORS['bg']};
            }}
            """
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("今日专注 Session")
        title.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {COLORS['text']};")
        layout.addWidget(title)

        detail_widget = TimelineWidget(
            max_rows=max(len(self._sessions), self._max_rows),
            show_title=False,
            open_detail_on_more=False,
            min_effective_seconds=self._min_effective_seconds,
            parent=dialog,
        )
        detail_widget.set_sessions(list(self._sessions), self._display_name_mapping)
        detail_widget.more_label.setVisible(False)
        layout.addWidget(detail_widget, 1)

        close_button = QPushButton("关闭")
        close_button.setCursor(Qt.PointingHandCursor)
        close_button.setStyleSheet(
            f"""
            QPushButton {{
                padding: 8px 18px;
                border-radius: 10px;
                border: 1px solid {COLORS['border']};
                color: {COLORS['text']};
                background: {COLORS['panel_bg']};
                font-size: 13px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                border-color: {COLORS['primary']};
            }}
            """
        )
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, 0, Qt.AlignRight)

        self._detail_dialog = dialog
        dialog.show()

    def _render_rows(self) -> None:
        while self._rows:
            row = self._rows.pop()
            self._content_layout.removeWidget(row)
            row.deleteLater()

        if not self._sessions:
            placeholder = QLabel("暂无足够长的专注 Session")
            placeholder.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
            self._content_layout.insertWidget(0, placeholder)
            self._rows.append(placeholder)
            self.more_label.setVisible(False)
            return

        displayed_sessions = list(self._sessions) if self._sort_by_value else list(reversed(self._sessions))
        if not self._expanded:
            displayed_sessions = displayed_sessions[: self._max_rows]

        for session in displayed_sessions:
            category_name = session.get("category_name") or "其他"
            category_key = session.get("category_key") or "other"
            color = self.CATEGORY_COLORS.get(category_name, get_category_color(category_key))
            row = self._build_session_card(session, color)
            self._content_layout.insertWidget(self._content_layout.count() - 1, row)
            self._rows.append(row)

        has_more = len(self._sessions) > self._max_rows
        self.more_label.setVisible(has_more)
        self.more_label.setEnabled(has_more)
        if has_more:
            if self._open_detail_on_more:
                self.more_label.setText(f"查看全部 Session ({len(self._sessions)}) ↗")
            else:
                self.more_label.setText("收起 ↑" if self._expanded else "查看更多 ↓")


class TrendChartWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setMinimumHeight(282)
        self._mode = "today"
        self._series: dict[str, list] = {"today": [], "7d": [], "30d": []}
        self._labels: dict[str, list[str]] = {"today": [], "7d": [], "30d": []}
        self._weekday_indices: dict[str, list[int]] = {"today": [], "7d": [], "30d": []}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 8)
        root.setSpacing(4)

        header = QHBoxLayout()
        self._title_label = QLabel("时间趋势（分钟）")
        self._title_label.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {COLORS['text']};")
        header.addWidget(self._title_label)
        header.addStretch()

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._mode_buttons: dict[str, QPushButton] = {}
        for mode, text in [("today", "今日"), ("7d", "近7天"), ("30d", "近30天")]:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"""
                QPushButton {{
                    padding: 3px 9px;
                    border-radius: 6px;
                    border: 1px solid {COLORS['border']};
                    color: {COLORS['text_secondary']};
                    background: {COLORS['panel_bg']};
                    font-size: 12px;
                }}
                QPushButton:checked {{
                    background: {COLORS['primary']};
                    color: white;
                    border-color: {COLORS['primary']};
                }}
                """
            )
            button.clicked.connect(lambda _, current_mode=mode: self.set_mode(current_mode))
            header.addWidget(button)
            self.group.addButton(button)
            self._mode_buttons[mode] = button
            if mode == "today":
                button.setChecked(True)
        root.addLayout(header)

        self.canvas = _TrendCanvas()
        self.canvas.setMinimumHeight(208)
        root.addWidget(self.canvas, 1)

        cmp_color = COLORS["text_muted"]
        self._cmp_legend = QLabel(
            f"<span>── 今日</span>  "
            f"<span style='color:{cmp_color}'>- - 昨日</span>"
        )
        self._cmp_legend.setStyleSheet(
            f"font-size: 10px; color: {COLORS['text_secondary']}; padding-left: 2px;"
        )
        self._cmp_legend.setVisible(False)
        root.addWidget(self._cmp_legend)

    def set_mode(self, mode: str) -> None:
        if mode in self._series:
            self._mode = mode
            button = self._mode_buttons.get(mode)
            if button is not None and not button.isChecked():
                button.setChecked(True)
            self._apply_series()
            unit = "分钟" if mode in {"today", "7d"} else "小时"
            self._title_label.setText(f"时间趋势（{unit}）")
            if mode == "today":
                cmp_color = COLORS["text_muted"]
                self._cmp_legend.setText(
                    f"<span>── 今日</span>  "
                    f"<span style='color:{cmp_color}'>- - 昨日</span>"
                )
                self._cmp_legend.setVisible(bool(self._yesterday_today))
            elif mode == "7d":
                week_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                parts = [
                    f"<span style='color:{self.canvas._weekday_colors[idx]}'>── {label}</span>"
                    for idx, label in enumerate(week_labels)
                ]
                self._cmp_legend.setText("  ".join(parts))
                self._cmp_legend.setVisible(True)
            else:
                self._cmp_legend.setVisible(False)

    def _apply_series(self) -> None:
        compare = self._yesterday_today if self._mode == "today" else []
        self.canvas.set_series(
            self._series[self._mode],
            self._labels.get(self._mode, []),
            self._mode,
            compare,
            self._weekday_indices.get(self._mode, []),
        )

    def set_data(self, today: list, yesterday_today: list, seven_days: list, thirty_days: list) -> None:
        self._series["today"] = today
        self._series["7d"] = seven_days
        self._series["30d"] = thirty_days
        self._yesterday_today = yesterday_today or []

        self._labels["today"] = ["0h", "", "2h", "", "4h", "", "6h", "", "8h", "", "10h", "", "12h", "", "14h", "", "16h", "", "18h", "", "20h", "", "22h", ""]
        self._labels["7d"] = list(self._labels["today"])

        today_date = date.today()
        self._weekday_indices["7d"] = [
            (today_date - timedelta(days=6 - i)).weekday()
            for i in range(7)
        ]

        markers = []
        for i in range(30):
            d = today_date - timedelta(days=29-i)
            markers.append(f"{d.month}/{d.day}" if i % 3 == 0 else "")
        self._labels["30d"] = markers
        self._weekday_indices["today"] = []
        self._weekday_indices["30d"] = []

        self._apply_series()


class _TrendCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._points: list[float] = []
        self._labels: list[str] = []
        self._mode = "today"
        self._compare_points: list[float] = []
        self._week_series: list[list[float]] = []
        self._weekday_indices: list[int] = []
        self._weekday_colors = [
            COLORS["weekday_mon"],
            COLORS["weekday_tue"],
            COLORS["weekday_wed"],
            COLORS["weekday_thu"],
            COLORS["weekday_fri"],
            COLORS["weekday_sat"],
            COLORS["weekday_sun"],
        ]

    def set_series(
        self,
        points: list,
        labels: list[str] | None = None,
        mode: str = "today",
        compare_points: list | None = None,
        weekday_indices: list[int] | None = None,
    ) -> None:
        self._week_series = []
        if mode == "7d" and points and isinstance(points[0], (list, tuple)):
            self._week_series = [
                [max(0.0, float(value)) for value in day_points]
                for day_points in points
            ]
            self._points = [max((series[idx] for series in self._week_series), default=0.0) for idx in range(24)]
        else:
            self._points = [max(0.0, float(point)) for point in points]
        self._labels = labels or []
        self._mode = mode
        self._compare_points = [max(0.0, float(p)) for p in (compare_points or [])]
        self._weekday_indices = list(weekday_indices or [])
        self.update()

    def _series_state(self) -> str:
        if not self._points:
            return "empty"
        if self._mode == "7d" and self._week_series:
            valid_count = sum(1 for series in self._week_series for value in series if value > 0)
            return "chart" if valid_count > 0 else "empty"
        valid_count = sum(1 for value in self._points if value > 0)
        if valid_count == 0:
            return "empty"
        if self._mode == "today" and valid_count < 3:
            return "accumulating"
        return "chart"

    def _uses_hour_units(self) -> bool:
        return self._mode == "30d"

    def _compute_y_axis_max(self, max_value: float) -> float:
        if self._mode == "today":
            y_max = max_value * 1.25
            if y_max < 1:
                y_max = 1.0
            return float(max(10, int(y_max) + 1))
        if self._mode == "7d":
            rounded = int((max_value + 29) // 30) * 30
            return float(max(30, rounded))
        y_max = max_value * 1.25
        if y_max < 1:
            y_max = 1.0
        y_max = round(y_max + 0.5, 1)
        return max(1.0, y_max)

    def _weekday_line_style(self, weekday: int, active: bool) -> dict[str, float | int]:
        is_weekend = weekday in {5, 6}
        if is_weekend:
            return {"width": 2.6 if active else 2.2, "alpha": 255 if active else 220}
        return {"width": 2.0 if active else 1.5, "alpha": 210 if active else 150}

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        chart_rect = r.adjusted(42, 6, -14, -30)

        state = self._series_state()
        if state == "empty":
            self._draw_empty(painter, r, "暂无趋势数据")
            return
        if state == "accumulating":
            self._draw_empty(painter, r, "数据积累中\n使用一段时间后将显示趋势")
            return

        max_value = max(self._points)
        if self._mode == "7d" and self._week_series:
            max_value = max(max(series) for series in self._week_series)
        y_max = self._compute_y_axis_max(max_value)

        # Grid lines
        painter.setPen(QPen(QColor(COLORS["border"]), 1, Qt.DashLine))
        for i in range(5):
            y = int(chart_rect.top() + i * chart_rect.height() / 4.0)
            painter.drawLine(chart_rect.left(), y, chart_rect.right(), y)

        # Y-axis labels
        painter.setPen(QColor(COLORS["text_muted"]))
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        is_hours = self._uses_hour_units()
        for i in range(5):
            y = int(chart_rect.top() + i * chart_rect.height() / 4.0)
            val = y_max * (4 - i) / 4
            if is_hours:
                label = f"{val:.1f}h"
            else:
                label = str(int(val))
            painter.drawText(QRectF(0, y - 7, 34, 14), Qt.AlignRight | Qt.AlignVCenter, label)

        if self._mode == "7d":
            self._draw_weekday_lines(painter, chart_rect, y_max)
            self._draw_x_axis_labels(painter, chart_rect)
            return

        # Compute chart points
        step = chart_rect.width() / max(len(self._points) - 1, 1)
        chart_points = []
        for index, value in enumerate(self._points):
            x = chart_rect.left() + index * step
            y = chart_rect.bottom() - (value / y_max) * chart_rect.height()
            chart_points.append(QPointF(x, y))

        # Area fill (only for > 5 points)
        if len(self._points) > 5:
            fill_path = QPainterPath()
            fill_path.moveTo(chart_rect.left(), chart_rect.bottom())
            for pt in chart_points:
                fill_path.lineTo(pt)
            fill_path.lineTo(chart_rect.right(), chart_rect.bottom())
            fill_path.closeSubpath()
            fill_color = QColor(COLORS["success_green"])
            fill_color.setAlpha(25)
            painter.setBrush(fill_color)
            painter.setPen(Qt.NoPen)
            painter.drawPath(fill_path)

        # Line
        line_path = QPainterPath()
        line_path.moveTo(chart_points[0])
        for pt in chart_points[1:]:
            line_path.lineTo(pt)
        painter.setPen(QPen(QColor(COLORS["success_green"]), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(line_path)

        # Yesterday comparison line (today mode only, dashed)
        if self._mode == "today" and self._compare_points and len(self._compare_points) == len(self._points):
            cmp_points = []
            for index, value in enumerate(self._compare_points):
                x = chart_rect.left() + index * step
                y = chart_rect.bottom() - (value / y_max) * chart_rect.height()
                cmp_points.append(QPointF(x, y))
            cmp_path = QPainterPath()
            cmp_path.moveTo(cmp_points[0])
            for pt in cmp_points[1:]:
                cmp_path.lineTo(pt)
            cmp_pen = QPen(QColor(COLORS["text_muted"]), 1.5, Qt.DashLine)
            cmp_pen.setDashPattern([6, 4])
            painter.setPen(cmp_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(cmp_path)

        # Dots
        dot_color = QColor(COLORS["success_green"])
        dot_color.setAlpha(220)
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot_color)
        for pt in chart_points:
            painter.drawEllipse(pt, 2.5, 2.5)

        self._draw_x_axis_labels(painter, chart_rect)

    def _draw_weekday_lines(self, painter: QPainter, chart_rect: QRectF, y_max: float) -> None:
        if not self._week_series:
            return
        step = chart_rect.width() / max(24 - 1, 1)
        for index, series in enumerate(self._week_series):
            weekday = self._weekday_indices[index] if index < len(self._weekday_indices) else index
            color = QColor(self._weekday_colors[weekday % 7])
            style = self._weekday_line_style(weekday, index == len(self._week_series) - 1)
            color.setAlpha(int(style["alpha"]))
            points = []
            for hour, value in enumerate(series[:24]):
                x = chart_rect.left() + hour * step
                y = chart_rect.bottom() - (value / y_max) * chart_rect.height()
                points.append(QPointF(x, y))
            if not points:
                continue
            path = QPainterPath()
            path.moveTo(points[0])
            for pt in points[1:]:
                path.lineTo(pt)
            pen = QPen(color, float(style["width"]))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            dot_radius = 2.4 if weekday in {5, 6} else 1.8
            for pt in points:
                painter.drawEllipse(pt, dot_radius, dot_radius)

    def _draw_x_axis_labels(self, painter: QPainter, chart_rect: QRectF) -> None:
        if self._labels and len(self._labels) == len(self._points):
            xfont = painter.font()
            xfont.setPixelSize(9)
            painter.setFont(xfont)
            painter.setPen(QColor(COLORS["text_secondary"]))
            step = chart_rect.width() / max(len(self._points) - 1, 1)
            for index, label in enumerate(self._labels):
                if not label:
                    continue
                x = chart_rect.left() + index * step
                painter.drawText(QRectF(x - 24, chart_rect.bottom() + 6, 48, 18),
                                 Qt.AlignCenter, label)

    def _draw_empty(self, painter: QPainter, rect: QRectF, text: str) -> None:
        painter.setPen(QColor(COLORS["text_muted"]))
        font = painter.font()
        font.setPixelSize(13)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, text)


class TopAppListWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setMinimumHeight(236)
        self._rows: list[tuple[QLabel, QLabel, QProgressBar, QLabel]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)

        title = QLabel("软件使用 TOP5")
        title.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {COLORS['text']};")
        root.addWidget(title)

        self.rows_container = QVBoxLayout()
        self.rows_container.setSpacing(12)
        root.addLayout(self.rows_container)
        root.addStretch()

        for rank in range(1, 6):
            layout, icon_label, name_label, progress_bar, duration_label = self._build_row(rank)
            self.rows_container.addLayout(layout)
            self._rows.append((icon_label, name_label, progress_bar, duration_label))

    def _build_row(self, rank: int):
        layout = QHBoxLayout()
        layout.setSpacing(10)

        rank_label = QLabel(str(rank))
        rank_label.setFixedWidth(18)
        rank_label.setStyleSheet(f"font-size: 15px; color: {COLORS['text_secondary']}; font-weight: 700;")
        layout.addWidget(rank_label)

        icon_label = QLabel("")
        icon_label.setFixedSize(20, 20)
        icon_label.setStyleSheet(f"background: {COLORS['panel_bg']}; border-radius: 5px;")
        layout.addWidget(icon_label)

        name_label = QLabel("--")
        name_label.setMinimumWidth(96)
        name_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text']}; font-weight: 600;")
        layout.addWidget(name_label)

        progress_bar = QProgressBar()
        progress_bar.setTextVisible(False)
        progress_bar.setRange(0, 100)
        progress_bar.setFixedHeight(8)
        progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background: {COLORS['panel_bg']};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {COLORS['primary']};
                border-radius: 3px;
            }}
            """
        )
        layout.addWidget(progress_bar, 1)

        duration_label = QLabel("--")
        duration_label.setFixedWidth(68)
        duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        duration_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        layout.addWidget(duration_label)

        return layout, icon_label, name_label, progress_bar, duration_label

    def set_items(self, items: list[tuple[str, str, int, QIcon | None]]) -> None:
        max_seconds = max((seconds for _, _, seconds, _ in items), default=1)
        for index in range(5):
            if index < len(items):
                process_name, display_name, seconds, icon = items[index]
                self._rows[index][0].setPixmap(icon.pixmap(18, 18) if icon else QIcon().pixmap(18, 18))
                self._rows[index][1].setText(_compact_app_name(display_name))
                self._rows[index][1].setToolTip(process_name if display_name != process_name else "")
                self._rows[index][2].setValue(int(round((seconds / max_seconds) * 100)))
                self._rows[index][3].setText(fmt_seconds(seconds))
            else:
                self._rows[index][0].clear()
                self._rows[index][1].setText("--")
                self._rows[index][2].setValue(0)
                self._rows[index][3].setText("--")


class DistributionLegend(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self._rows: list[QWidget] = []

    def set_items(self, items: list[tuple[str, int, str]], total_seconds: int) -> None:
        while self._rows:
            row = self._rows.pop()
            self.layout.removeWidget(row)
            row.deleteLater()

        total = max(1, total_seconds)
        for name, seconds, color in items:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            icon = QLabel("●")
            icon.setFixedWidth(16)
            icon.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 700;")
            row_layout.addWidget(icon)

            name_label = QLabel(name)
            name_label.setMinimumWidth(72)
            name_label.setStyleSheet(
                f"font-size: 14px; font-weight: 700; color: {COLORS['text']};"
            )
            row_layout.addWidget(name_label)

            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            bar.setValue(int(round(seconds / total * 100)))
            bar.setFixedHeight(8)
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background: {COLORS['panel_bg']};
                    border: none;
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background: {color};
                    border-radius: 4px;
                }}
            """)
            row_layout.addWidget(bar, 1)

            time_label = QLabel(fmt_seconds(seconds))
            time_label.setFixedWidth(60)
            time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            time_label.setStyleSheet(
                f"font-size: 14px; color: {COLORS['text']}; font-weight: 700;"
            )
            row_layout.addWidget(time_label)

            pct_label = QLabel(f"{int(round(seconds / total * 100))}%")
            pct_label.setFixedWidth(36)
            pct_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pct_label.setStyleSheet(
                f"font-size: 13px; color: {COLORS['text_secondary']}; font-weight: 600;"
            )
            row_layout.addWidget(pct_label)

            self.layout.addWidget(row)
            self._rows.append(row)


def _compact_app_name(name: str, limit: int = 18) -> str:
    if not name:
        return "--"
    if len(name) <= limit:
        return name
    return f"{name[: limit - 1]}..."


def _timeline_duration_text(session: dict) -> str:
    seconds = (
        session.get("effective_seconds", 0)
        or session.get("idle_seconds", 0)
        or session.get("duration_seconds", 0)
        or 0
    )
    return fmt_seconds(seconds)
