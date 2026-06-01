"""Reusable widgets for the dashboard home page."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...utils import fmt_seconds
from ..style import COLORS, DASHBOARD_CARD_STYLE


class MiniSparkline(QWidget):
    """Compact line sparkline used in metric cards."""

    def __init__(self, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = QColor(color)
        self._points: list[float] = []
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_points(self, points: Iterable[float]):
        values = [max(0.0, float(p)) for p in points]
        self._points = values
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
            if i == 0:
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
    """Top metric card with icon, value, delta and sparkline."""

    def __init__(self, title: str, icon: str, accent: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._accent = accent
        self.setStyleSheet(DASHBOARD_CARD_STYLE)
        self.setFixedHeight(132)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(5)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {COLORS['text_secondary']};"
        )
        root.addWidget(title_label)

        value_row = QHBoxLayout()
        value_row.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(34, 34)
        icon_label.setStyleSheet(
            f"""
            QLabel {{
                border-radius: 17px;
                background: {accent};
                color: white;
                font-size: 16px;
                font-weight: 700;
            }}
            """
        )
        value_row.addWidget(icon_label, 0)

        self.value_label = QLabel("--")
        self.value_label.setMinimumWidth(0)
        self.value_label.setStyleSheet(
            f"font-size: 28px; font-weight: 800; color: {COLORS['text']};"
        )
        value_row.addWidget(self.value_label, 1)
        root.addLayout(value_row)

        self.delta_label = QLabel("较昨日 --")
        self.delta_label.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']};"
        )
        root.addWidget(self.delta_label)

        self.sparkline = MiniSparkline(accent)
        root.addWidget(self.sparkline)

    def set_value(self, value_text: str, delta_text: str):
        self.value_label.setText(value_text)
        self.delta_label.setText(delta_text)

    def set_sparkline(self, points: Iterable[float]):
        self.sparkline.set_points(points)


class DonutChartWidget(QWidget):
    """Simple donut chart for time distribution."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._total_seconds = 0
        self._segments: list[tuple[str, int, str]] = []
        self.setMinimumSize(150, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

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

        base_pen = QPen(QColor("#E4EAF4"), ring_width)
        base_pen.setCapStyle(Qt.FlatCap)
        painter.setPen(base_pen)
        painter.drawArc(rect, 0, 360 * 16)

        if self._total_seconds <= 0:
            self._draw_center_text(painter, "0分", "总时长")
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

        self._draw_center_text(painter, fmt_seconds(self._total_seconds), "总时长")

    def _draw_center_text(self, painter: QPainter, value: str, caption: str):
        painter.setPen(QColor(COLORS["text"]))
        painter.setFont(self.font())
        f = painter.font()
        f.setPointSize(15)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(self.rect().adjusted(0, -10, 0, 0), Qt.AlignCenter, value)

        f2 = painter.font()
        f2.setPointSize(10)
        f2.setBold(False)
        painter.setFont(f2)
        painter.setPen(QColor(COLORS["text_muted"]))
        painter.drawText(self.rect().adjusted(0, 24, 0, 0), Qt.AlignCenter, caption)


class ScoreGaugeWidget(QWidget):
    """Circular score gauge."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._score: int | None = None
        self._accent = COLORS["coding_green"]
        self.setMinimumSize(150, 138)

    def set_score(self, score: int | None, accent: str):
        self._score = score
        self._accent = accent
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = max(112, min(self.width(), self.height()) - 22)
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        width = max(11.0, side * 0.1)

        base = QPen(QColor("#E4E9F3"), width)
        base.setCapStyle(Qt.RoundCap)
        painter.setPen(base)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        if self._score is None:
            value = 0
        else:
            value = max(0, min(100, int(self._score)))

        fg = QPen(QColor(self._accent), width)
        fg.setCapStyle(Qt.RoundCap)
        painter.setPen(fg)
        painter.drawArc(rect, 225 * 16, int(-270 * 16 * (value / 100.0)))

        painter.setPen(QColor(COLORS["text"]))
        f = painter.font()
        f.setPointSize(24)
        f.setBold(True)
        painter.setFont(f)
        label = "--" if self._score is None else str(value)
        painter.drawText(self.rect().adjusted(0, -8, 0, 0), Qt.AlignCenter, label)

        f2 = painter.font()
        f2.setPointSize(10)
        f2.setBold(False)
        painter.setFont(f2)
        painter.setPen(QColor(COLORS["text_muted"]))
        painter.drawText(self.rect().adjusted(0, 28, 0, 0), Qt.AlignCenter, "/ 100")


class TrendChartWidget(QWidget):
    """Simple line chart for minute trend."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._points: list[float] = []
        self.setMinimumHeight(180)

    def set_points(self, points: Iterable[float]):
        self._points = [max(0.0, float(p)) for p in points]
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        content = self.rect().adjusted(16, 10, -16, -16)
        painter.setPen(QColor("#E4EAF4"))
        for i in range(5):
            y = content.top() + i * content.height() / 4
            painter.drawLine(content.left(), int(y), content.right(), int(y))

        if len(self._points) < 2:
            return

        max_v = max(self._points) or 1.0
        step = content.width() / max(1, len(self._points) - 1)
        line_path = QPainterPath()
        fill_path = QPainterPath()

        for i, value in enumerate(self._points):
            x = content.left() + i * step
            y = content.bottom() - (value / max_v) * content.height()
            p = QPointF(x, y)
            if i == 0:
                line_path.moveTo(p)
                fill_path.moveTo(content.left(), content.bottom())
                fill_path.lineTo(p)
            else:
                line_path.lineTo(p)
                fill_path.lineTo(p)

        fill_path.lineTo(content.right(), content.bottom())
        fill_path.closeSubpath()

        painter.fillPath(fill_path, QColor(47, 110, 248, 42))
        pen = QPen(QColor(COLORS["primary"]), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPath(line_path)


class TopAppListWidget(QFrame):
    """Top app list card with horizontal bars."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(DASHBOARD_CARD_STYLE)
        self.setFixedHeight(235)
        self._rows: list[tuple[QLabel, QProgressBar, QLabel]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

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
            self._rows.append((row[1], row[2], row[3]))

    def _build_row(self, rank: int):
        layout = QHBoxLayout()
        layout.setSpacing(8)

        idx = QLabel(str(rank))
        idx.setFixedWidth(16)
        idx.setStyleSheet(f"font-size: 15px; color: {COLORS['text_secondary']}; font-weight: 700;")
        layout.addWidget(idx)

        name = QLabel("--")
        name.setMinimumWidth(90)
        name.setStyleSheet(f"font-size: 13px; color: {COLORS['text']};")
        layout.addWidget(name, 1)

        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setFixedHeight(8)
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background: {COLORS['panel_bg']};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {COLORS['primary']};
                border-radius: 4px;
            }}
            """
        )
        layout.addWidget(bar, 1)

        duration = QLabel("--")
        duration.setFixedWidth(66)
        duration.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        duration.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
        layout.addWidget(duration)
        return layout, name, bar, duration

    def set_items(self, items: list[tuple[str, int]]):
        max_seconds = max((seconds for _, seconds in items), default=1)
        for i in range(5):
            if i < len(items):
                name, seconds = items[i]
                pct = int(round((seconds / max_seconds) * 100)) if max_seconds else 0
                self._rows[i][0].setText(_compact_app_name(name))
                self._rows[i][1].setValue(max(0, min(100, pct)))
                self._rows[i][2].setText(fmt_seconds(seconds))
            else:
                self._rows[i][0].setText("--")
                self._rows[i][1].setValue(0)
                self._rows[i][2].setText("--")


class DistributionLegend(QWidget):
    """Legend list with category name, duration and percent."""

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

            percent = int(round(seconds / total * 100))
            pct_label = QLabel(f"{percent}%")
            pct_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text_muted']};")
            line.addWidget(pct_label, 0, 3, Qt.AlignRight)

            line.setColumnStretch(1, 1)
            self.layout.addWidget(row)
            self._rows.append(row)


def _compact_app_name(name: str, limit: int = 18) -> str:
    """Keep app names readable in the narrow TOP5 column."""
    if not name:
        return "--"
    if len(name) <= limit:
        return name
    return f"{name[: limit - 1]}..."
