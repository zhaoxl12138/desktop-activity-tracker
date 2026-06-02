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
from ..style import COLORS, DASHBOARD_CARD_STYLE, get_category_color


class MiniSparkline(QWidget):
    def __init__(self, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(color)
        self._points: list[float] = []
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_points(self, points: Iterable[float]):
        self._points = [max(0.0, float(p)) for p in points]
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        if len(self._points) < 2:
            return
        w = self.width()
        h = self.height()
        margin = 3
        max_v = max(self._points) or 1.0
        step = (w - margin * 2) / max(1, len(self._points) - 1)
        path = QPainterPath()
        for i, value in enumerate(self._points):
            x = margin + i * step
            y = h - margin - (value / max_v) * (h - margin * 2)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
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
        self.setFixedHeight(140)
        self.setMinimumWidth(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(5)
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
        self.value_label.setStyleSheet(f"font-size: 28px; font-weight: 800; color: {COLORS['text']};")
        value_row.addWidget(self.value_label, 1)
        root.addLayout(value_row)

        self.delta_label = QLabel("较昨日 --")
        self.delta_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']};")
        root.addWidget(self.delta_label)
        self.sparkline = MiniSparkline(accent)
        root.addWidget(self.sparkline)

    def set_value(self, value_text: str, delta_text: str):
        self.value_label.setText(value_text)
        self.delta_label.setText(delta_text)

    def set_warning(self, active: bool):
        self.value_label.setStyleSheet(
            f"font-size: 28px; font-weight: 800; color: {COLORS['danger_red'] if active else COLORS['text']};"
        )

    def set_sparkline(self, points: Iterable[float]):
        self.sparkline.set_points(points)


class DonutChartWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._total_seconds = 0
        self._segments: list[tuple[str, int, str]] = []
        self.setMinimumSize(150, 150)

    def set_data(self, total_seconds: int, segments: list[tuple[str, int, str]]):
        self._total_seconds = max(0, int(total_seconds or 0))
        self._segments = segments
        self.update()

    def paintEvent(self, event):  # noqa: N802
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


class ScoreGaugeWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._score: int | None = None
        self._accent = COLORS["coding_green"]

    def set_score(self, score: int | None, accent: str):
        self._score = score
        self._accent = accent
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        side = max(96, min(156, min(w, h) - 22))
        rect = QRectF((w - side) / 2, (h - side) / 2, side, side)
        width = max(8.0, side * 0.09)
        painter.setPen(QPen(QColor(COLORS["border"]), width))
        painter.drawArc(rect, 225 * 16, -270 * 16)
        value = 0 if self._score is None else max(0, min(100, int(self._score)))
        painter.setPen(QPen(QColor(self._accent), width))
        painter.drawArc(rect, 225 * 16, int(-270 * 16 * (value / 100.0)))


class FocusTimelineBarWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._minute_colors = [COLORS["idle_gray"]] * 1440
        self.setFixedHeight(28)

    def set_minutes(self, minute_colors: list[str]):
        if len(minute_colors) == 1440:
            self._minute_colors = minute_colors
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(2, 5, -2, -5)
        minute_w = rect.width() / 1440.0
        start = 0
        color = self._minute_colors[0]
        for i in range(1, 1440):
            if self._minute_colors[i] != color:
                left = rect.left() + start * minute_w
                right = rect.left() + i * minute_w
                painter.fillRect(QRectF(left, rect.top(), max(1.0, right - left), rect.height()), QColor(color))
                start = i
                color = self._minute_colors[i]
        left = rect.left() + start * minute_w
        painter.fillRect(QRectF(left, rect.top(), max(1.0, rect.right() - left + 1), rect.height()), QColor(color))
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
        self.setObjectName("dashboardCard")
        self.setStyleSheet("QFrame#dashboardCard { background: transparent; border: none; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("今日时间线")
        title.setStyleSheet(f"font-size: 28px; font-weight: 800; color: {COLORS['text']};")
        root.addWidget(title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 2, 0)
        self._content_layout.setSpacing(4)
        self._content_layout.addStretch()
        self.scroll.setWidget(self._content)
        root.addWidget(self.scroll, 1)
        self.more_label = QLabel("查看更多 ↓")
        self.more_label.setAlignment(Qt.AlignHCenter)
        self.more_label.setStyleSheet(f"font-size: 26px; color: {COLORS['primary']}; font-weight: 700;")
        root.addWidget(self.more_label)

    def set_sessions(self, sessions, display_name_mapping=None):
        while self._rows:
            row = self._rows.pop()
            self._content_layout.removeWidget(row)
            row.deleteLater()
        if not sessions:
            placeholder = QLabel("暂无会话数据")
            placeholder.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
            self._content_layout.insertWidget(0, placeholder)
            self._rows.append(placeholder)
            return
        mapping = display_name_mapping or {}
        for s in list(reversed(sessions))[: self._max_rows]:
            cat_name = s.get("category_name") or "其他"
            cat_key = s.get("category_key") or "other"
            color = self.CATEGORY_COLORS.get(cat_name, get_category_color(cat_key))
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            start, end = s.get("start_time", ""), s.get("end_time", "")
            time_label = QLabel(f"{start[-8:-3]}-{end[-8:-3]}")
            time_label.setFixedWidth(88)
            time_label.setStyleSheet(f"font-size: 22px; color: {COLORS['text_secondary']}; font-weight: 600;")
            row_layout.addWidget(time_label)
            dot = QFrame()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
            row_layout.addWidget(dot)
            proc = s.get("process_name") or ""
            app_label = QLabel(mapping.get(proc, proc) or proc)
            app_label.setStyleSheet(f"font-size: 22px; color: {COLORS['text']}; font-weight: 700;")
            row_layout.addWidget(app_label)
            cat_label = QLabel(cat_name)
            cat_label.setStyleSheet(f"font-size: 20px; color: {color}; font-weight: 700;")
            row_layout.addWidget(cat_label, 1)
            eff = s.get("effective_seconds", 0) or 0
            dur_label = QLabel(f"{max(1, eff // 60)}分钟")
            dur_label.setFixedWidth(68)
            dur_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            dur_label.setStyleSheet(f"font-size: 20px; color: {COLORS['text_muted']};")
            row_layout.addWidget(dur_label)
            self._content_layout.insertWidget(self._content_layout.count() - 1, row)
            self._rows.append(row)


class TrendChartWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(DASHBOARD_CARD_STYLE)
        self.setFixedHeight(215)
        self._mode = "today"
        self._series = {"today": [], "7d": [], "30d": []}
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        header = QHBoxLayout()
        title = QLabel("时间趋势（分钟）")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        header.addWidget(title)
        header.addStretch()
        self.group = QButtonGroup(self)
        for mode, text in [("today", "今日"), ("7d", "近7天"), ("30d", "近30天")]:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"padding: 4px 10px; border-radius: 8px; border: 1px solid {COLORS['border']}; color: {COLORS['text_secondary']}; background: {COLORS['panel_bg']};"
                f"QPushButton:checked {{ background: {COLORS['primary']}; color: white; border-color: {COLORS['primary']}; }}"
            )
            btn.clicked.connect(lambda _, m=mode: self.set_mode(m))
            header.addWidget(btn)
            self.group.addButton(btn)
            if mode == "today":
                btn.setChecked(True)
        root.addLayout(header)
        self.canvas = _TrendCanvas()
        root.addWidget(self.canvas, 1)

    def set_mode(self, mode: str):
        if mode in self._series:
            self._mode = mode
            self.canvas.set_series(self._series[mode])

    def set_data(self, today: list[int], seven_days: list[int], thirty_days: list[int]):
        self._series["today"] = today
        self._series["7d"] = seven_days
        self._series["30d"] = thirty_days
        self.canvas.set_series(self._series[self._mode])


class _TrendCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._points: list[int] = []

    def set_series(self, points: list[int]):
        self._points = [max(0, int(v)) for v in points]
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        if len(self._points) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(8, 8, -8, -14)
        painter.setPen(QPen(QColor(COLORS["border"]), 1))
        for i in range(5):
            y = r.top() + i * r.height() / 4.0
            painter.drawLine(r.left(), int(y), r.right(), int(y))
        max_v = max(self._points) or 1
        step = r.width() / (len(self._points) - 1)
        points = []
        for i, v in enumerate(self._points):
            points.append(QPointF(r.left() + i * step, r.bottom() - (v / max_v) * r.height()))
        path = QPainterPath()
        path.moveTo(points[0])
        for p in points[1:]:
            path.lineTo(p)
        painter.setPen(QPen(QColor(COLORS["primary"]), 2))
        painter.drawPath(path)


class TopAppListWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(DASHBOARD_CARD_STYLE)
        self.setFixedHeight(248)
        self._rows: list[tuple[QLabel, QLabel, QProgressBar, QLabel]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        title = QLabel("软件使用 TOP5")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {COLORS['text']};")
        root.addWidget(title)
        self.rows_container = QVBoxLayout()
        self.rows_container.setSpacing(8)
        root.addLayout(self.rows_container)
        root.addStretch()
        for rank in range(1, 6):
            row = self._build_row(rank)
            self.rows_container.addLayout(row[0])
            self._rows.append((row[1], row[2], row[3], row[4]))

    def _build_row(self, rank: int):
        layout = QHBoxLayout()
        idx = QLabel(str(rank))
        idx.setFixedWidth(16)
        idx.setStyleSheet(f"font-size: 15px; color: {COLORS['text_secondary']}; font-weight: 700;")
        layout.addWidget(idx)
        icon = QLabel("")
        icon.setFixedSize(18, 18)
        icon.setStyleSheet(f"background: {COLORS['panel_bg']}; border-radius: 4px;")
        layout.addWidget(icon)
        name = QLabel("--")
        name.setMinimumWidth(100)
        name.setStyleSheet(f"font-size: 13px; color: {COLORS['text']};")
        layout.addWidget(name)
        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setFixedHeight(8)
        bar.setStyleSheet(
            f"QProgressBar {{ background: {COLORS['panel_bg']}; border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {COLORS['primary']}; border-radius: 4px; }}"
        )
        layout.addWidget(bar, 1)
        duration = QLabel("--")
        duration.setFixedWidth(66)
        duration.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        duration.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
        layout.addWidget(duration)
        return layout, icon, name, bar, duration

    def set_items(self, items: list[tuple[str, str, int, QIcon | None]]):
        max_seconds = max((seconds for _, _, seconds, _ in items), default=1)
        for i in range(5):
            if i < len(items):
                process_name, display_name, seconds, icon = items[i]
                self._rows[i][0].setPixmap(icon.pixmap(18, 18) if icon else QIcon().pixmap(18, 18))
                self._rows[i][1].setText(_compact_app_name(display_name))
                self._rows[i][1].setToolTip(process_name if display_name != process_name else "")
                self._rows[i][2].setValue(int(round((seconds / max_seconds) * 100)))
                self._rows[i][3].setText(fmt_seconds(seconds))
            else:
                self._rows[i][0].clear()
                self._rows[i][1].setText("--")
                self._rows[i][2].setValue(0)
                self._rows[i][3].setText("--")


class DistributionLegend(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)
        self._rows: list[QWidget] = []

    def set_items(self, items: list[tuple[str, int, str]], total_seconds: int):
        while self._rows:
            row = self._rows.pop()
            self.layout.removeWidget(row)
            row.deleteLater()
        total = max(1, total_seconds)
        for name, seconds, color in items:
            row = QWidget()
            line = QGridLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 13px;")
            line.addWidget(dot, 0, 0)
            name_label = QLabel(name)
            name_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
            line.addWidget(name_label, 0, 1)
            time_label = QLabel(fmt_seconds(seconds))
            time_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text']}; font-weight: 600;")
            line.addWidget(time_label, 0, 2, Qt.AlignRight)
            pct_label = QLabel(f"{int(round(seconds / total * 100))}%")
            pct_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text_muted']};")
            line.addWidget(pct_label, 0, 3, Qt.AlignRight)
            line.setColumnStretch(1, 1)
            self.layout.addWidget(row)
            self._rows.append(row)


def _compact_app_name(name: str, limit: int = 18) -> str:
    if not name:
        return "--"
    return name if len(name) <= limit else f"{name[: limit - 1]}..."
