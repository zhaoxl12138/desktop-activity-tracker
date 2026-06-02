"""Reusable widgets for the dashboard home page."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
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


class MiniSparkline(QWidget):
    def __init__(self, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(color)
        self._points: list[float] = []
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_points(self, points: Iterable[float]) -> None:
        self._points = [max(0.0, float(point)) for point in points]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if len(self._points) < 2:
            return

        width = self.width()
        height = self.height()
        margin = 3
        max_value = max(self._points) or 1.0
        step = (width - margin * 2) / max(1, len(self._points) - 1)

        path = QPainterPath()
        for index, value in enumerate(self._points):
            x = margin + index * step
            y = height - margin - (value / max_value) * (height - margin * 2)
            if index == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self._color, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)


class MetricCard(QFrame):
    def __init__(self, title: str, icon: str, accent: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(
            f"""
            QFrame#dashboardCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {COLORS['card_bg_alt']}, stop:1 {COLORS['card_bg']});
                border: 1px solid {accent};
                border-radius: 18px;
            }}
            """
        )
        self.setFixedHeight(128)
        self.setMinimumWidth(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 11, 14, 10)
        root.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {COLORS['text_secondary']};"
        )
        root.addWidget(title_label)

        value_row = QHBoxLayout()
        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(34, 34)
        icon_label.setStyleSheet(
            f"border-radius: 17px; background: {accent}; color: white; font-size: 16px; font-weight: 700;"
        )
        value_row.addWidget(icon_label)

        self.value_label = QLabel("--")
        self.value_label.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {COLORS['text']};")
        value_row.addWidget(self.value_label, 1)
        root.addLayout(value_row)

        self.delta_label = QLabel("较昨日 --")
        self.delta_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
        root.addWidget(self.delta_label)

        self.sparkline = MiniSparkline(accent)
        root.addWidget(self.sparkline)

    def set_value(self, value_text: str, delta_text: str) -> None:
        self.value_label.setText(value_text)
        self.delta_label.setText(delta_text)

    def set_warning(self, active: bool) -> None:
        color = COLORS["danger_red"] if active else COLORS["text"]
        self.value_label.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {color};")

    def set_sparkline(self, points: Iterable[float]) -> None:
        self.sparkline.set_points(points)


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

        side = max(120, min(self.width(), self.height()) - 18)
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        ring_width = max(12.0, side * 0.12)

        base_pen = QPen(QColor(COLORS["border"]), ring_width)
        painter.setPen(base_pen)
        painter.drawArc(rect, 0, 360 * 16)

        if self._total_seconds <= 0:
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


class FocusTimelineBarWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._minute_colors = [COLORS["idle_gray"]] * 1440
        self.setFixedHeight(28)

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
        "学习/工作": COLORS["coding_green"],
        "视频娱乐": COLORS["video_orange"],
        "社交通讯": COLORS["social_purple"],
        "挂机": COLORS["idle_gray"],
        "离开": COLORS["idle_gray"],
        "空闲": COLORS["idle_gray"],
        "其他": COLORS["ai_blue"],
    }

    def __init__(self, max_rows: int = 6, parent: QWidget | None = None):
        super().__init__(parent)
        self._max_rows = max_rows
        self._rows: list[QWidget] = []
        self._sessions: list[dict] = []
        self._display_name_mapping = {}
        self._expanded = False
        self.setObjectName("dashboardCard")
        self.setStyleSheet("QFrame#dashboardCard { background: transparent; border: none; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        title = QLabel("今日时间线")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        root.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 2, 0)
        self._content_layout.setSpacing(6)
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
                padding: 2px 0 0 0;
            }}
            QPushButton:hover {{
                color: {COLORS['primary_hover']};
            }}
            """
        )
        self.more_label.clicked.connect(self.toggle_expanded)
        root.addWidget(self.more_label, 0, Qt.AlignHCenter)

    def set_sessions(self, sessions, display_name_mapping=None) -> None:
        self._sessions = list(sessions or [])
        self._display_name_mapping = display_name_mapping or {}
        self._expanded = False
        self._render_rows()

    def toggle_expanded(self) -> None:
        if len(self._sessions) <= self._max_rows:
            return
        self._expanded = not self._expanded
        self._render_rows()

    def _render_rows(self) -> None:
        while self._rows:
            row = self._rows.pop()
            self._content_layout.removeWidget(row)
            row.deleteLater()

        if not self._sessions:
            placeholder = QLabel("暂无会话数据")
            placeholder.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
            self._content_layout.insertWidget(0, placeholder)
            self._rows.append(placeholder)
            self.more_label.setVisible(True)
            self.more_label.setEnabled(False)
            self.more_label.setText("查看更多 ↓")
            return

        displayed_sessions = list(reversed(self._sessions))
        if not self._expanded:
            displayed_sessions = displayed_sessions[: self._max_rows]

        for session in displayed_sessions:
            category_name = session.get("category_name") or "其他"
            category_key = session.get("category_key") or "other"
            color = self.CATEGORY_COLORS.get(category_name, get_category_color(category_key))

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            start = session.get("start_time", "") or ""
            end = session.get("end_time", "") or ""
            time_label = QLabel(f"{start[-8:-3]}-{end[-8:-3]}")
            time_label.setFixedWidth(92)
            time_label.setStyleSheet(
                f"font-size: 13px; color: {COLORS['text_secondary']}; font-weight: 600;"
            )
            row_layout.addWidget(time_label)

            dot = QFrame()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
            row_layout.addWidget(dot)

            process_name = session.get("process_name") or ""
            app_label = QLabel(self._display_name_mapping.get(process_name, process_name) or process_name)
            app_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text']}; font-weight: 700;")
            row_layout.addWidget(app_label)

            category_label = QLabel(category_name)
            category_label.setStyleSheet(f"font-size: 12px; color: {color}; font-weight: 700;")
            row_layout.addWidget(category_label, 1)

            effective_seconds = session.get("effective_seconds", 0) or 0
            duration_label = QLabel(f"{max(1, effective_seconds // 60)}分钟")
            duration_label.setFixedWidth(60)
            duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            duration_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
            row_layout.addWidget(duration_label)

            self._content_layout.insertWidget(self._content_layout.count() - 1, row)
            self._rows.append(row)

        has_more = len(self._sessions) > self._max_rows
        self.more_label.setVisible(True)
        self.more_label.setEnabled(has_more)
        if not has_more:
            self.more_label.setText("查看更多 ↓")
        else:
            self.more_label.setText("收起 ↑" if self._expanded else "查看更多 ↓")


class TrendChartWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setFixedHeight(196)
        self._mode = "today"
        self._series = {"today": [], "7d": [], "30d": []}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("时间趋势（分钟）")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        header.addWidget(title)
        header.addStretch()

        self.group = QButtonGroup(self)
        for mode, text in [("today", "今日"), ("7d", "近7天"), ("30d", "近30天")]:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"""
                QPushButton {{
                    padding: 4px 10px;
                    border-radius: 8px;
                    border: 1px solid {COLORS['border']};
                    color: {COLORS['text_secondary']};
                    background: {COLORS['panel_bg']};
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
            if mode == "today":
                button.setChecked(True)
        root.addLayout(header)

        self.canvas = _TrendCanvas()
        root.addWidget(self.canvas, 1)

    def set_mode(self, mode: str) -> None:
        if mode in self._series:
            self._mode = mode
            self.canvas.set_series(self._series[mode])

    def set_data(self, today: list[int], seven_days: list[int], thirty_days: list[int]) -> None:
        self._series["today"] = today
        self._series["7d"] = seven_days
        self._series["30d"] = thirty_days
        self.canvas.set_series(self._series[self._mode])


class _TrendCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._points: list[int] = []

    def set_series(self, points: list[int]) -> None:
        self._points = [max(0, int(point)) for point in points]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if len(self._points) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -14)

        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        for index in range(5):
            y = rect.top() + index * rect.height() / 4.0
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        max_value = max(self._points) or 1
        step = rect.width() / (len(self._points) - 1)
        points = []
        for index, value in enumerate(self._points):
            x = rect.left() + index * step
            y = rect.bottom() - (value / max_value) * rect.height()
            points.append(QPointF(x, y))

        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)

        painter.setPen(QPen(QColor(COLORS["primary"]), 2))
        painter.drawPath(path)


class TopAppListWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setFixedHeight(238)
        self._rows: list[tuple[QLabel, QLabel, QProgressBar, QLabel]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(8)

        title = QLabel("软件使用 TOP5")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        root.addWidget(title)

        self.rows_container = QVBoxLayout()
        self.rows_container.setSpacing(10)
        root.addLayout(self.rows_container)
        root.addStretch()

        for rank in range(1, 6):
            layout, icon_label, name_label, progress_bar, duration_label = self._build_row(rank)
            self.rows_container.addLayout(layout)
            self._rows.append((icon_label, name_label, progress_bar, duration_label))

    def _build_row(self, rank: int):
        layout = QHBoxLayout()
        layout.setSpacing(8)

        rank_label = QLabel(str(rank))
        rank_label.setFixedWidth(16)
        rank_label.setStyleSheet(
            f"font-size: 15px; color: {COLORS['text_secondary']}; font-weight: 700;"
        )
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
        progress_bar.setFixedHeight(7)
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
        duration_label.setFixedWidth(66)
        duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        duration_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
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
        self.layout.setSpacing(6)
        self._rows: list[QWidget] = []

    def set_items(self, items: list[tuple[str, int, str]], total_seconds: int) -> None:
        while self._rows:
            row = self._rows.pop()
            self.layout.removeWidget(row)
            row.deleteLater()

        total = max(1, total_seconds)
        for name, seconds, color in items:
            row = QWidget()
            line = QGridLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setHorizontalSpacing(6)
            line.setVerticalSpacing(0)

            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 13px;")
            line.addWidget(dot, 0, 0)

            name_label = QLabel(name)
            name_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
            line.addWidget(name_label, 0, 1)

            time_label = QLabel(fmt_seconds(seconds))
            time_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text']}; font-weight: 600;")
            line.addWidget(time_label, 0, 2, Qt.AlignRight)

            percent_label = QLabel(f"{int(round(seconds / total * 100))}%")
            percent_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text_muted']};")
            line.addWidget(percent_label, 0, 3, Qt.AlignRight)

            line.setColumnStretch(1, 1)
            self.layout.addWidget(row)
            self._rows.append(row)


def _compact_app_name(name: str, limit: int = 18) -> str:
    if not name:
        return "--"
    if len(name) <= limit:
        return name
    return f"{name[: limit - 1]}..."
