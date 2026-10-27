"""Reusable widgets for the dashboard home page."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
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
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ...utils import fmt_seconds, parse_nonnegative_int
from .. import style as ui_style
from .elided_label import ElidedLabel
from .ui_primitives import MetricCell
from .history_card_widgets import HistoryMetricCell, history_range_text, history_captured_text
from ..style import COLORS, get_category_color


class DonutChartWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._total_seconds = 0
        self._primary_seconds = 0
        self._primary_label = "有效时长"
        self._segments: list[tuple[str, int, str]] = []
        self.setMinimumSize(150, 150)

    def set_data(
        self,
        total_seconds: int,
        segments: list[tuple[str, int, str]],
        *,
        primary_seconds: int | None = None,
        primary_label: str | None = None,
    ) -> None:
        self._total_seconds = parse_nonnegative_int(total_seconds) or 0
        self._primary_seconds = (
            self._total_seconds
            if primary_seconds is None
            else (parse_nonnegative_int(primary_seconds) or 0)
        )
        self._primary_label = str(primary_label or "有效时长")
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

        # Center text: primary duration with explicit snapshot semantics.
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text_muted"]))
        painter.drawText(QRectF(rect.left(), rect.center().y() - 18, rect.width(), 16),
                         Qt.AlignCenter, self._primary_label)

        font.setPixelSize(17)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(COLORS["text"]))
        painter.drawText(QRectF(rect.left(), rect.center().y(), rect.width(), 22),
                         Qt.AlignCenter, fmt_seconds(self._primary_seconds))


class ActiveRatioRingWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._ratio = 0
        self._ratio_label = "有效时间占比"
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
        painter.drawText(
            QRectF(rect.left(), rect.center().y() + 12, rect.width(), 24),
            Qt.AlignCenter,
            self._ratio_label,
        )


class FocusTimelineBarWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._minute_colors = [COLORS["timeline_idle"]] * 1440
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
        "办公": COLORS["coding_green"],
        "工作学习": COLORS["coding_green"],
        "视频娱乐": COLORS["video_orange"],
        "娱乐休闲": COLORS["video_orange"],
        "社交通讯": COLORS["social_purple"],
        "浏览器": COLORS["browser_amber"],
        "系统工具": COLORS["tools_cyan"],
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

    @staticmethod
    def _merge_sessions(sessions: list[dict]) -> list[dict]:
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
                background: {COLORS['panel_bg_alt']};
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

        app_label = ElidedLabel(self._session_display_label(session))
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
                background: {COLORS['panel_bg_alt']};
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


class SessionTop3Widget(QFrame):
    """Table-layout top sessions list with detail dialog."""

    RANKS = ["🥇", "🥈", "🥉"]
    MIN_EFFECTIVE_SECONDS = 5 * 60

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet("QFrame#dashboardCard { background: transparent; border: none; }")
        self._sessions: list[dict] = []
        self._display_name_mapping: dict = {}
        self._row_frames: list[QFrame] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header row
        header = self._build_header()
        root.addWidget(header)

        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: transparent;")
        rows_layout = QVBoxLayout(self._rows_container)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(0)
        self._rows_layout = rows_layout
        root.addWidget(self._rows_container)

        self.more_btn = QPushButton()
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.setFlat(True)
        self.more_btn.setStyleSheet(
            f"""
            QPushButton {{
                font-size: 13px;
                color: {COLORS['primary']};
                font-weight: 700;
                border: none;
                background: transparent;
                padding: 6px 0 0 0;
            }}
            QPushButton:hover {{
                color: {COLORS['primary_hover']};
            }}
            """
        )
        self.more_btn.clicked.connect(self._open_detail_dialog)
        root.addWidget(self.more_btn, 0, Qt.AlignHCenter)

    def _v_sep(self) -> QFrame:
        """Thin vertical separator for table columns."""
        sep = QFrame()
        sep.setFixedWidth(3)
        sep.setMinimumHeight(1)
        sep.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        sep.setStyleSheet(f"background: {COLORS['border_light']}; border: none;")
        return sep

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(28)
        hdr.setStyleSheet(
            f"background: {COLORS['panel_bg_alt']};"
            f"border-bottom: 1px solid {COLORS['border_light']};"
        )
        layout = QHBoxLayout(hdr)
        layout.setContentsMargins(10, 0, 12, 0)
        layout.setSpacing(0)

        header_specs = [
            ("排名", 44),
            ("应用程序", None),   # stretch
            ("分类", 110),
            ("开始", 80),
            ("结束", 80),
            ("时长", 90),
        ]
        for i, (text, width) in enumerate(header_specs):
            if i > 0:
                layout.addWidget(self._v_sep())
            lbl = QLabel(text)
            if width:
                lbl.setFixedWidth(width)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"font-size: 12px; color: {COLORS['text_secondary']}; font-weight: 700;"
                f"border: none; background: transparent;"
            )
            layout.addWidget(lbl, 0 if width else 1)

        return hdr

    def set_sessions(self, sessions: list[dict], display_name_mapping: dict | None = None) -> None:
        merged = TimelineWidget._merge_sessions(list(sessions or []))
        filtered = [
            s for s in merged
            if (s.get("effective_seconds", 0) or 0) >= self.MIN_EFFECTIVE_SECONDS
        ]
        filtered.sort(
            key=lambda s: (
                -int(s.get("effective_seconds", 0) or 0),
                str(s.get("end_time", "") or ""),
            )
        )
        self._sessions = filtered
        self._display_name_mapping = display_name_mapping or {}
        self._render()

    def _render(self) -> None:
        for f in self._row_frames:
            self._rows_layout.removeWidget(f)
            f.deleteLater()
        self._row_frames.clear()

        top_n = self._sessions[:6]

        if not top_n:
            placeholder = QLabel(" 暂无足够长的专注 Session")
            placeholder.setStyleSheet(
                f"font-size: 12px; color: {COLORS['text_muted']}; padding: 8px 0;"
            )
            self._rows_layout.addWidget(placeholder)
            self._row_frames.append(placeholder)
            self.more_btn.setVisible(False)
            return

        for rank, session in enumerate(top_n):
            row = self._build_row(rank, session)
            self._rows_layout.addWidget(row)
            self._row_frames.append(row)

        total = len(self._sessions)
        self.more_btn.setText(f"查看全部 Session ({total}) ↗")
        self.more_btn.setVisible(total > 6)

    # Medal accent colors for top-3 podium rows
    MEDAL_COLORS = ["#FFD700", "#C0C0C0", "#CD7F32"]  # gold, silver, bronze
    MEDAL_BG = ["rgba(255,215,0,0.06)", "rgba(192,192,192,0.04)", "rgba(205,127,50,0.04)"]

    def _build_row(self, rank: int, session: dict) -> QFrame:
        category_key = str(session.get("category_key", "") or "other")
        accent_color = get_category_color(category_key)
        category_name = str(session.get("category_name", "") or "其他")
        is_podium = rank < 3

        row = QFrame()
        row.setFixedHeight(50)
        row.setObjectName("sessionTableRow")
        if is_podium:
            medal = self.MEDAL_COLORS[rank]
            medal_bg = self.MEDAL_BG[rank]
            row.setStyleSheet(
                f"""
                QFrame#sessionTableRow {{
                    background: {medal_bg};
                    border-left: 3px solid {medal};
                    border-bottom: 1px solid {COLORS['border']};
                }}
                QFrame#sessionTableRow:hover {{
                    background: {COLORS['panel_bg_alt']};
                }}
                """
            )
        else:
            row.setStyleSheet(
                f"""
                QFrame#sessionTableRow {{
                    background: transparent;
                    border-bottom: 1px solid {COLORS['border']};
                }}
                QFrame#sessionTableRow:hover {{
                    background: {COLORS['panel_bg_alt']};
                }}
                """
            )

        layout = QHBoxLayout(row)
        layout.setContentsMargins(10, 0, 12, 0)
        layout.setSpacing(0)

        # ── Rank badge ──
        rank_text = self.RANKS[rank] if rank < 3 else str(rank + 1)
        rank_badge = QLabel(rank_text)
        rank_badge.setFixedSize(28, 28)
        rank_badge.setAlignment(Qt.AlignCenter)
        if rank < 3:
            rank_badge.setStyleSheet(
                f"font-size: 16px; border: none; background: transparent;"
            )
        else:
            rank_badge.setStyleSheet(
                f"font-size: 12px; color: {COLORS['text_secondary']}; font-weight: 700;"
                f"border: 1.5px solid {COLORS['border']}; border-radius: 14px;"
                f"background: {COLORS['panel_bg_alt']};"
            )
        rank_wrapper = QWidget()
        rank_wrapper.setFixedWidth(44)
        rank_w_layout = QHBoxLayout(rank_wrapper)
        rank_w_layout.setContentsMargins(0, 0, 0, 0)
        rank_w_layout.setAlignment(Qt.AlignCenter)
        rank_w_layout.addWidget(rank_badge)
        layout.addWidget(rank_wrapper)
        layout.addWidget(self._v_sep())

        # ── App icon + name + window title ──
        process_name = str(session.get("process_name", "") or "")
        display_name = self._display_name_mapping.get(process_name, process_name) or process_name or "未知"
        window_title = str(session.get("normalized_title", "") or session.get("window_title", "") or "").strip()

        if is_podium:
            app_style = (
                f"font-size: 13px; color: {COLORS['text']}; font-weight: 800;"
                f"border: none; background: transparent;"
            )
        else:
            app_style = (
                f"font-size: 13px; color: {COLORS['text']}; font-weight: 600;"
                f"border: none; background: transparent;"
            )
        app_label = ElidedLabel(
            f"{display_name} ({window_title})"
            if window_title and window_title.lower() != display_name.lower()
            else display_name
        )
        app_label.setAlignment(Qt.AlignCenter)
        app_label.setStyleSheet(app_style)
        app_label.setToolTip(f"{display_name} — {window_title}" if window_title else display_name)
        layout.addWidget(app_label, 1)
        layout.addWidget(self._v_sep())

        # ── Category with color dot ──
        cat_widget = QWidget()
        cat_widget.setFixedWidth(110)
        cat_layout = QHBoxLayout(cat_widget)
        cat_layout.setContentsMargins(0, 0, 0, 0)
        cat_layout.setSpacing(6)
        cat_layout.setAlignment(Qt.AlignCenter)

        dot = QLabel("●")
        dot.setStyleSheet(f"font-size: 10px; color: {accent_color}; border: none; background: transparent;")
        cat_layout.addWidget(dot)

        cat_label = QLabel(category_name)
        cat_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_secondary']}; font-weight: 600;"
            f"border: none; background: transparent;"
        )
        cat_layout.addWidget(cat_label)
        layout.addWidget(cat_widget)
        layout.addWidget(self._v_sep())

        # ── Start time ──
        start = str(session.get("start_time", "") or "")
        start_short = start[11:16] if len(start) >= 16 else start[-5:]
        start_label = QLabel(start_short)
        start_label.setFixedWidth(80)
        start_label.setAlignment(Qt.AlignCenter)
        start_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_secondary']};"
            f"border: none; background: transparent;"
        )
        layout.addWidget(start_label)
        layout.addWidget(self._v_sep())

        # ── End time ──
        end = str(session.get("end_time", "") or "")
        end_short = end[11:16] if len(end) >= 16 else end[-5:]
        end_label = QLabel(end_short)
        end_label.setFixedWidth(80)
        end_label.setAlignment(Qt.AlignCenter)
        end_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_secondary']};"
            f"border: none; background: transparent;"
        )
        layout.addWidget(end_label)
        layout.addWidget(self._v_sep())

        # ── Duration capsule ──
        effective = int(session.get("effective_seconds", 0) or 0)
        dur_label = QLabel(fmt_seconds(effective))
        dur_label.setFixedWidth(90)
        dur_label.setAlignment(Qt.AlignCenter)
        dur_label.setStyleSheet(
            f"font-size: 12px; color: #fff; font-weight: 800;"
            f"background: {accent_color}; border-radius: 6px;"
            f"padding: 3px 0;"
        )
        layout.addWidget(dur_label)

        return row

    def _open_detail_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("今日专注 Session")
        dialog.setModal(True)
        dialog.resize(980, 720)
        dialog.setStyleSheet(f"QDialog {{ background: {COLORS['bg']}; }}")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("今日专注 Session")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: 800; color: {COLORS['text']};"
        )
        layout.addWidget(title)

        detail_widget = TimelineWidget(
            max_rows=max(len(self._sessions), 5),
            show_title=False,
            open_detail_on_more=False,
            min_effective_seconds=0,
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
                background: {COLORS['panel_bg_alt']};
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

        dialog.show()


class TrustedInsightCard(QFrame):
    """Compact, plain-text renderer for one trusted local insight."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setMinimumHeight(96)
        self.setMaximumHeight(124)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.title_label = ElidedLabel("", max_lines=1)
        self.title_label.setTextFormat(Qt.PlainText)
        self.title_label.setStyleSheet(
            f"font-size: 14px; font-weight: 800; color: {COLORS['text']};"
        )
        header.addWidget(self.title_label, 1)

        self.confidence_label = QLabel("")
        self.confidence_label.setTextFormat(Qt.PlainText)
        self.confidence_label.setAlignment(Qt.AlignCenter)
        self.confidence_label.setMinimumWidth(58)
        header.addWidget(self.confidence_label, 0, Qt.AlignTop)
        root.addLayout(header)

        self.evidence_label = ElidedLabel("", max_lines=2)
        self.evidence_label.setTextFormat(Qt.PlainText)
        self.evidence_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_secondary']};"
        )
        root.addWidget(self.evidence_label)

        self.action_label = ElidedLabel("", max_lines=1)
        self.action_label.setTextFormat(Qt.PlainText)
        self.action_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['primary']}; font-weight: 700;"
        )
        root.addWidget(self.action_label)

        self.set_insight(None)

    def set_insight(self, insight: dict[str, object] | None) -> None:
        if not insight:
            self.title_label.setText("洞察积累中")
            self.evidence_label.setText("继续记录以形成可靠基线")
            self.action_label.setText("")
            self._set_confidence("数据不足", "low")
            self._set_compact(True)
            return
        self.title_label.setText(str(insight.get("title", "今日建议")))
        self.evidence_label.setText(str(insight.get("evidence", "")))
        self.action_label.setText(str(insight.get("action", "")))
        confidence = str(insight.get("confidence", "low"))
        confidence_text = {
            "high": "高可信",
            "medium": "中可信",
            "low": "低可信",
        }.get(confidence, "低可信")
        self._set_confidence(
            confidence_text,
            confidence if confidence in {"high", "medium", "low"} else "low",
        )
        self._set_compact(confidence == "low")

    def _set_compact(self, compact: bool) -> None:
        self.setMinimumHeight(58 if compact else 96)
        self.setMaximumHeight(72 if compact else 124)
        self.evidence_label.setMaxLines(1 if compact else 2)
        self.action_label.setVisible(not compact and bool(self.action_label.fullText()))

    def _set_confidence(self, text: str, confidence: str) -> None:
        color = {
            "high": COLORS["success_green"],
            "medium": COLORS["warning_yellow"],
            "low": COLORS["text_muted"],
        }[confidence]
        background = (
            COLORS["success_bg"]
            if confidence == "high"
            else COLORS["warning_bg"]
            if confidence == "medium"
            else COLORS["panel_bg_alt"]
        )
        self.confidence_label.setText(text)
        self.confidence_label.setStyleSheet(
            "font-size: 11px; font-weight: 800; padding: 2px 7px; "
            f"color: {color}; background: {background}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 8px;"
        )


class RhythmComparisonCard(QFrame):
    """Shows work-engagement rhythm without repeating category distribution."""

    day_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setMinimumHeight(223)
        self.setMaximumHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._mode = "today"
        self._payload: dict[str, dict] = {}
        self._captured_at = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        self._title_label = QLabel("工作节奏对比")
        self._title_label.setTextFormat(Qt.PlainText)
        self._title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 800; color: {COLORS['text']};"
        )
        header.addWidget(self._title_label)
        header.addStretch(1)

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._mode_buttons: dict[str, QPushButton] = {}
        for mode, text in (("today", "今日"), ("7d", "近7天"), ("30d", "近30天")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"""
                QPushButton {{
                    padding: 3px 8px; border-radius: 6px;
                    border: 1px solid {COLORS['border']};
                    color: {COLORS['text_secondary']};
                    background: {COLORS['panel_bg_alt']}; font-size: 11px;
                }}
                QPushButton:checked {{
                    background: {COLORS['primary']}; color: white;
                    border-color: {COLORS['primary']};
                }}
                """
            )
            button.clicked.connect(
                lambda _checked=False, current_mode=mode: self.set_mode(current_mode)
            )
            header.addWidget(button)
            self.group.addButton(button)
            self._mode_buttons[mode] = button
        self._mode_buttons["today"].setChecked(True)

        self._status_label = QLabel("数据积累中")
        self._status_label.setTextFormat(Qt.PlainText)
        self._status_label.setAlignment(Qt.AlignCenter)
        header.addWidget(self._status_label)
        root.addLayout(header)

        self._conclusion_label = QLabel("节奏数据积累中")
        self._conclusion_label.setTextFormat(Qt.PlainText)
        self._conclusion_label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {COLORS['text_secondary']};"
        )
        root.addWidget(self._conclusion_label)

        self.canvas = _RhythmCanvas()
        self.canvas.day_activated.connect(self.day_activated.emit)
        self.canvas.setMinimumHeight(110)
        root.addWidget(self.canvas, 1)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self._metric_labels: list[tuple[QLabel, QLabel, QLabel]] = []
        for _ in range(3):
            cell = HistoryMetricCell()
            label, value, delta = cell.label, cell.value, cell.detail
            metrics.addWidget(cell, 1)
            self._metric_labels.append((label, value, delta))
        root.addLayout(metrics)

        # Compatibility alias for callers that previously exposed the yellow notice.
        self.classification_notice = QLabel("")
        self.classification_notice.setVisible(False)
        self.set_data({})

    def _dynamic_labels(self) -> list[QLabel]:
        labels = [self._title_label, self._status_label, self._conclusion_label]
        labels.extend(label for group in self._metric_labels for label in group)
        return labels

    def _legend_text(self) -> str:
        return ""

    def set_data(self, payload: dict | None) -> None:
        self._captured_at = str(dict(payload or {}).get("captured_at") or "")
        self._payload = {
            str(key): dict(value)
            for key, value in dict(payload or {}).items()
            if key in {"today", "7d", "30d"} and isinstance(value, dict)
        }
        self._apply_mode()

    def set_mode(self, mode: str) -> None:
        if mode not in {"today", "7d", "30d"}:
            return
        self._mode = mode
        button = self._mode_buttons.get(mode)
        if button is not None and not button.isChecked():
            button.setChecked(True)
        self._apply_mode()

    def set_history_comparability(self, **_kwargs) -> None:
        """Compatibility shim; comparability is already encoded in rhythm payload."""

    def _apply_mode(self) -> None:
        data = self._payload.get(self._mode)
        if not data:
            self._title_label.setText("工作节奏对比")
            self._status_label.setText("数据积累中")
            self._set_status_style("waiting")
            self._conclusion_label.setText("节奏数据积累中")
            self.canvas.set_data({})
            self._set_metrics([])
            return
        self._title_label.setText(
            f"工作节奏 · {'近7天' if self._mode == '7d' else '近30天'}"
            if self._mode in {"7d", "30d"}
            else str(data.get("title", "工作节奏对比"))
        )
        status = dict(data.get("status", {}) or {})
        self._status_label.setText(str(status.get("label", "数据积累中")))
        self._set_status_style(str(status.get("kind", "waiting")))
        if self._mode in {"7d", "30d"} and history_range_text(data.get("date_range")):
            caption = "  ".join(part for part in (
                history_range_text(data.get("date_range")), history_captured_text(self._captured_at)
            ) if part)
        else:
            caption = str(data.get("conclusion", "节奏数据积累中"))
        self._conclusion_label.setText(caption)
        chart = dict(data.get("chart", {}) or {})
        chart["show_bar_duration_labels"] = self._mode == "7d"
        chart["day_activation_enabled"] = self._mode == "7d"
        period = data.get("date_range") or []
        if self._mode in {"7d", "30d"} and len(period) == 2:
            chart["today_date"] = period[-1]
        self.canvas.set_data(chart)
        self._set_metrics(list(data.get("metrics", []) or []))

    def _set_metrics(self, values: list[dict]) -> None:
        for index, (label, value, delta) in enumerate(self._metric_labels):
            historical = self._mode in {"7d", "30d"}
            value.setWordWrap(historical)
            delta.setWordWrap(historical)
            delta.setStyleSheet(
                f"font-size: 13px; font-weight: 600; color: {COLORS['text_secondary']};"
                if historical else f"font-size: 12px; color: {COLORS['text_muted']};"
            )
            item = dict(values[index]) if index < len(values) else {}
            text = ("日均时长", "最高一天", "总时长")[index] if self._mode in {"7d", "30d"} and item else str(item.get("label", ""))
            label.setText(text)
            value_text = str(item.get("value", "--"))
            if index == 1 and self._mode in {"7d", "30d"}:
                value_text = value_text.split()[0] if value_text.split() else "--"
            value.setText(value_text)
            delta_text = str(item.get("delta", ""))
            delta.setText(delta_text)
            delta.setVisible(bool(delta_text))

    def _set_status_style(self, kind: str) -> None:
        color = COLORS["primary"] if kind == "baseline" else COLORS["warning_yellow"] if kind == "break" else COLORS["text_muted"]
        self._status_label.setStyleSheet(
            f"font-size: 10px; font-weight: 800; color: {color}; "
            f"background: {COLORS['panel_bg_alt']}; border: 1px solid {COLORS['border']}; "
            "border-radius: 8px; padding: 2px 7px;"
        )


class _RhythmCanvas(QWidget):
    day_activated = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self._kind = "empty"
        self._state = "empty"
        self._data: dict = {}
        self._show_bar_duration_labels = False
        self._bar_duration_labels: list[str] = []
        self._bar_hit_rects: list[QRectF | None] = []

    def set_data(self, data: dict) -> None:
        self._data = dict(data or {})
        self._kind = str(self._data.get("kind", "empty") or "empty")
        values = self._data.get("current") if self._kind == "cumulative" else self._data.get("values")
        self._show_bar_duration_labels = bool(
            self._kind == "bars"
            and self._data.get("show_bar_duration_labels", False)
        )
        self._bar_duration_labels = [
            self._bar_duration_label(value)
            if self._show_bar_duration_labels
            else ""
            for value in (values or [])
        ]
        self._bar_hit_rects = [None] * len(values or [])
        self._state = "chart" if any(value is not None for value in (values or [])) else "empty"
        clickable = bool(self._data.get("day_activation_enabled") and self._data.get("dates"))
        if clickable and self._kind == "bars":
            self._state = "chart"
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        dates = self._data.get("dates") or []
        chart = self._chart_rect()
        width = chart.width()
        x = event.position().x() - chart.left()
        if (event.button() == Qt.LeftButton and self._kind == "bars"
                and self._data.get("day_activation_enabled") and dates
                and len(dates) == len(self._data.get("values") or [])
                and width > 0 and 0 <= x < width):
            index = min(len(dates) - 1, int(x / width * len(dates)))
            try:
                value = date.fromisoformat(str(dates[index])).isoformat()
            except (ValueError, TypeError):
                return
            self.day_activated.emit(value)
        super().mousePressEvent(event)

    def _chart_rect(self) -> QRectF:
        compact_bars = self._kind == "bars" and len(self._data.get("values") or []) <= 7
        return QRectF(self.rect()).adjusted(
            (8 if compact_bars else 24) if self._kind == "bars" else 54,
            22 if self._show_bar_duration_labels else 8,
            -12 if compact_bars else -28, -34,
        )

    def _bar_slot(self, index: int, chart: QRectF) -> QRectF:
        count = len(self._data.get("values") or [])
        if not 0 <= index < count:
            return QRectF()
        width = chart.width()/count
        return QRectF(chart.left()+index*width, chart.top(), width, chart.height())

    def _today_index(self) -> int | None:
        dates = self._data.get("dates") or []
        today = self._data.get("today_date")
        if (self._kind != "bars" or not today
                or len(dates) != len(self._data.get("values") or [])):
            return None
        try:
            return dates.index(today)
        except ValueError:
            return None

    @staticmethod
    def _bar_duration_label(value) -> str:
        seconds = parse_nonnegative_int(value) or 0
        if seconds <= 0:
            return ""
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        if hours:
            return f"{hours}h{minutes}m"
        return f"{minutes}m" if minutes else "<1m"

    def _tooltip_text_for_index(self, index: int) -> str:
        contexts = self._data.get("hover_contexts", [])
        context = contexts[index] if isinstance(contexts, (list, tuple)) and 0 <= index < len(contexts) else None
        if isinstance(context, dict):
            label = str(context.get("label", "") or "").strip()
            seconds = parse_nonnegative_int(context.get("seconds")) or 0
            if label and seconds > 0:
                return f"{label}\n参与 {_goal_duration(seconds)}"
        values = self._data.get("values") or []
        labels = self._data.get("labels") or []
        if self._kind == "bars" and 0 <= index < min(len(values), len(labels)):
            seconds = parse_nonnegative_int(values[index])
            return f"{labels[index]}\n工作参与 {_goal_duration(seconds)}" if seconds is not None else f"{labels[index]}\n暂无记录"
        return ""

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._kind == "bars":
            position = event.position()
            for index, rect in enumerate(self._bar_hit_rects):
                if rect is not None and rect.contains(position):
                    text = self._tooltip_text_for_index(index)
                    if text:
                        QToolTip.showText(event.globalPosition().toPoint(), text, self)
                        return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        QToolTip.hideText()
        super().leaveEvent(event)

    def _value_color(self, index: int) -> QColor:
        return QColor(COLORS["primary"])

    @staticmethod
    def _x_label_indices(count: int) -> list[int]:
        if count <= 0:
            return []
        if count <= 7:
            return list(range(count))
        step = max(1, math.ceil(count / 5))
        indices = list(range(0, count, step))
        if indices[-1] != count - 1:
            indices.append(count - 1)
        return indices[:6]

    @staticmethod
    def _segments(values: list) -> list[list[tuple[int, float]]]:
        result: list[list[tuple[int, float]]] = []
        active: list[tuple[int, float]] = []
        for index, value in enumerate(values):
            if value is None:
                if active:
                    result.append(active)
                    active = []
                continue
            active.append((index, max(0.0, float(value))))
        if active:
            result.append(active)
        return result

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        if self._state == "empty":
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(rect, Qt.AlignCenter, "节奏数据积累中")
            return
        chart = self._chart_rect()
        values = list(self._data.get("current", [])) if self._kind == "cumulative" else list(self._data.get("values", []))
        extra = []
        for key in ("baseline_low", "baseline_high", "baseline_median"):
            extra.extend(value for value in self._data.get(key, []) if value is not None)
        numeric = [float(value) for value in values if value is not None] + [float(value) for value in extra]
        y_max = max(180.0, max(numeric, default=0.0) * 1.15)
        grid_color = QColor(COLORS["border"])
        grid_color.setAlpha(140)
        painter.setPen(QPen(grid_color, 1, Qt.DashLine))
        for index in range(4):
            y = chart.top() + chart.height() * index / 3
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))
        self._draw_y_labels(painter, chart, y_max)
        if self._kind == "cumulative":
            self._draw_cumulative(painter, chart, y_max)
        elif self._kind == "bars":
            self._draw_bars(painter, chart, y_max)
        else:
            self._draw_weekly(painter, chart, y_max)
        self._draw_x_labels(painter, chart)

    def _point(self, chart: QRectF, index: int, count: int, value: float, y_max: float) -> QPointF:
        step = chart.width() / max(count - 1, 1)
        return QPointF(chart.left() + step * index, chart.bottom() - value / y_max * chart.height())

    def _draw_cumulative(self, painter: QPainter, chart: QRectF, y_max: float) -> None:
        current = list(self._data.get("current", []))
        low = list(self._data.get("baseline_low", []))
        high = list(self._data.get("baseline_high", []))
        median_values = list(self._data.get("baseline_median", []))
        if low and high:
            pairs = [(index, float(lo), float(hi)) for index, (lo, hi) in enumerate(zip(low, high)) if lo is not None and hi is not None]
            if len(pairs) > 1:
                path = QPainterPath()
                path.moveTo(self._point(chart, pairs[0][0], len(current), pairs[0][2], y_max))
                for index, _lo, hi in pairs[1:]:
                    path.lineTo(self._point(chart, index, len(current), hi, y_max))
                for index, lo, _hi in reversed(pairs):
                    path.lineTo(self._point(chart, index, len(current), lo, y_max))
                path.closeSubpath()
                fill = QColor("#6b8fb8")
                fill.setAlpha(50)
                painter.fillPath(path, fill)
        self._draw_line(painter, chart, median_values, y_max, QColor("#7792ae"), Qt.DashLine, 1.5)
        self._draw_line(painter, chart, current, y_max, QColor(COLORS["primary"]), Qt.SolidLine, 2.5)

    def _draw_bars(self, painter: QPainter, chart: QRectF, y_max: float) -> None:
        values = list(self._data.get("values", []))
        today_index = self._today_index()
        self._bar_hit_rects = [None] * len(values)
        for index, value in enumerate(values):
            slot = self._bar_slot(index, chart)
            if value is None:
                color = QColor(COLORS["text_secondary"] if index == today_index else COLORS["border_light"])
                painter.setPen(QPen(color, 1, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(QRectF(slot.left()+slot.width()*.28, chart.bottom()-3,
                                               slot.width()*.44, 3), 1, 1)
                continue
            painter.setPen(QPen(QColor(COLORS["text"]), 1.25) if index == today_index else Qt.NoPen)
            painter.setBrush(self._value_color(index))
            height = max(2.0, float(value) / y_max * chart.height())
            bar_rect = QRectF(
                slot.left() + slot.width() * 0.22,
                chart.bottom() - height,
                slot.width() * 0.56,
                height,
            )
            self._bar_hit_rects[index] = bar_rect
            painter.drawRoundedRect(bar_rect, 3, 3)
            duration_label = self._bar_duration_labels[index]
            if duration_label:
                painter.setPen(QColor(COLORS["text"]))
                duration_font = painter.font()
                duration_font.setPixelSize(11)
                duration_font.setBold(True)
                painter.setFont(duration_font)
                painter.drawText(
                    QRectF(
                        slot.left(),
                        max(0.0, chart.bottom() - height - 20),
                        slot.width(),
                        18,
                    ),
                    Qt.AlignCenter,
                    duration_label,
                )
                painter.setPen(Qt.NoPen)

    def _draw_weekly(self, painter: QPainter, chart: QRectF, y_max: float) -> None:
        values = list(self._data.get("values", []))
        for index in range(1, len(values)):
            previous = values[index - 1]
            current = values[index]
            if previous is None or current is None:
                continue
            color = (
                QColor(COLORS["primary"])
                if self._value_color(index - 1) == QColor(COLORS["primary"])
                and self._value_color(index) == QColor(COLORS["primary"])
                else QColor("#7792ae")
            )
            painter.setPen(QPen(color, 2.5, Qt.SolidLine))
            painter.drawLine(
                self._point(chart, index - 1, len(values), float(previous), y_max),
                self._point(chart, index, len(values), float(current), y_max),
            )
        painter.setPen(Qt.NoPen)
        for index, value in enumerate(values):
            if value is None:
                continue
            painter.setBrush(self._value_color(index))
            painter.drawEllipse(
                self._point(chart, index, len(values), float(value), y_max),
                3,
                3,
            )

    def _draw_line(self, painter: QPainter, chart: QRectF, values: list, y_max: float, color: QColor, style, width: float) -> None:
        for segment in self._segments(values):
            if len(segment) == 1:
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(self._point(chart, segment[0][0], len(values), segment[0][1], y_max), 3, 3)
                continue
            path = QPainterPath()
            path.moveTo(self._point(chart, segment[0][0], len(values), segment[0][1], y_max))
            for index, value in segment[1:]:
                path.lineTo(self._point(chart, index, len(values), value, y_max))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(color, width, style))
            painter.drawPath(path)

    def _draw_y_labels(self, painter: QPainter, chart: QRectF, y_max: float) -> None:
        if self._kind == "bars":
            return
        painter.setPen(QColor(COLORS["text_secondary"]))
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        for index in range(4):
            value = y_max * (3 - index) / 3
            minutes = round(value / 60)
            label = f"{minutes // 60}h" if minutes >= 60 and minutes % 60 == 0 else f"{minutes}m"
            y = chart.top() + chart.height() * index / 3
            painter.drawText(QRectF(0, y - 9, chart.left()-14, 18), Qt.AlignRight | Qt.AlignVCenter, label)

    def _draw_x_labels(self, painter: QPainter, chart: QRectF) -> None:
        labels = list(self._data.get("labels", []))
        if not labels:
            return
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        if self._kind == "cumulative":
            indices = [0, 12, 24, 36, 47]
        elif self._kind == "bars":
            count = min(len(labels), len(self._data.get("values") or []))
            indices = self._x_label_indices(count)
        else:
            indices = self._x_label_indices(len(labels))
        today_index = self._today_index()
        for index in indices:
            if index >= len(labels):
                continue
            font.setBold(index == today_index)
            painter.setFont(font)
            painter.setPen(QColor(COLORS["text"] if index == today_index else COLORS["text_secondary"]))
            if self._kind == "bars":
                slot = self._bar_slot(index, chart)
                label_width = slot.width() if count <= 7 else max(48, slot.width())
                label_rect = QRectF(slot.center().x()-label_width/2, chart.bottom()+8, label_width, 18)
            else:
                x = chart.left() + chart.width() * index / max(len(labels) - 1, 1)
                label_rect = QRectF(x-24, chart.bottom()+8, 48, 18)
            painter.drawText(label_rect, Qt.AlignCenter, str(labels[index]))


class TrendChartWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setMinimumHeight(230)
        self._mode = "today"
        self._series: dict[str, list] = {"today": [], "7d": [], "30d": []}
        self._labels: dict[str, list[str]] = {"today": [], "7d": [], "30d": []}
        self._weekday_indices: dict[str, list[int]] = {"today": [], "7d": [], "30d": []}
        self._work_today: list = []
        self._entertainment_today: list = []
        self._yesterday_today: list = []

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
                    background: {COLORS['panel_bg_alt']};
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

        self.classification_notice = QLabel(
            "分类规则已变化，分类趋势暂不可比"
        )
        self.classification_notice.setTextFormat(Qt.PlainText)
        self.classification_notice.setWordWrap(True)
        self.classification_notice.setStyleSheet(
            f"font-size: 11px; color: {COLORS['warning_yellow']}; font-weight: 700;"
        )
        self.classification_notice.setVisible(False)
        root.addWidget(self.classification_notice)
        self._classification_comparable = True
        self._metric_break = False

        self.canvas = _TrendCanvas()
        self.canvas.setMinimumHeight(160)
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
        self._thirty_day_metric = "effective"
        root.addWidget(self._cmp_legend)

    def set_classification_comparable(self, comparable: bool) -> None:
        self.set_history_comparability(
            metric_break=self._metric_break,
            classification_comparable=comparable,
        )

    def set_history_comparability(
        self,
        *,
        metric_break: bool,
        classification_comparable: bool,
    ) -> None:
        self._metric_break = bool(metric_break)
        self._classification_comparable = bool(classification_comparable)
        if self._metric_break:
            self.classification_notice.setText(
                "计量口径已变化，历史参与趋势暂不可比"
            )
        else:
            self.classification_notice.setText(
                "分类规则已变化，分类趋势暂不可比"
            )
        self.classification_notice.setVisible(
            self._metric_break or not self._classification_comparable
        )

    def set_mode(self, mode: str) -> None:
        if mode in self._series:
            self._mode = mode
            button = self._mode_buttons.get(mode)
            if button is not None and not button.isChecked():
                button.setChecked(True)
            self._apply_series()
            self._update_title()
            self._update_legend()

    def _update_title(self) -> None:
        unit = "分钟" if self._mode in {"today", "7d"} else "小时"
        if self._mode == "30d":
            prefix = (
                "参与" if self._thirty_day_metric == "engaged" else "有效"
            )
            self._title_label.setText(f"{prefix}时间趋势（{unit}）")
        else:
            self._title_label.setText(f"时间趋势（{unit}）")

    def _update_legend(self) -> None:
        if self._mode == "today":
            green = COLORS["coding_green"]
            orange = COLORS["video_orange"]
            muted = COLORS["text_muted"]
            self._cmp_legend.setText(
                f"<span style='color:{green}'>── 工作学习</span>  "
                f"<span style='color:{orange}'>── 娱乐休闲</span>  "
                f"<span style='color:{green}'>- - 昨日工作</span>  "
                f"<span style='color:{orange}'>- - 昨日娱乐</span>"
            )
            self._cmp_legend.setVisible(True)
        elif self._mode == "7d":
            week_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            parts = [
                f"<span style='color:{self.canvas._weekday_colors[idx]}'>── {label}</span>"
                for idx, label in enumerate(week_labels)
            ]
            self._cmp_legend.setText("  ".join(parts))
            self._cmp_legend.setVisible(True)
        else:
            label = (
                "每日参与时间"
                if self._thirty_day_metric == "engaged"
                else "每日有效时间"
            )
            self._cmp_legend.setText(
                f"<span style='color:{COLORS["coding_green"]}'>{label}</span>"
            )
            self._cmp_legend.setVisible(True)

    def _apply_series(self) -> None:
        compare = self._yesterday_today if self._mode in ("7d", "30d") else []
        self.canvas.set_series(
            self._series[self._mode],
            self._labels.get(self._mode, []),
            self._mode,
            compare,
            self._weekday_indices.get(self._mode, []),
            work_points=self._work_today if self._mode == "today" else None,
            entertainment_points=self._entertainment_today if self._mode == "today" else None,
            yesterday_work=getattr(self, '_yesterday_work', []),
            yesterday_entertainment=getattr(self, '_yesterday_entertainment', []),
        )

    def set_data(self, today: list, yesterday_today: list, seven_days: list,
                 thirty_days: list, work_today: list | None = None,
                 entertainment_today: list | None = None,
                 yesterday_work: list | None = None,
                 yesterday_entertainment: list | None = None,
                 seven_day_labels: list | None = None,
                 thirty_day_metric: str = "effective") -> None:
        self._series["today"] = today
        self._series["7d"] = seven_days
        self._series["30d"] = thirty_days
        self._yesterday_today = yesterday_today or []
        self._work_today = work_today or []
        self._entertainment_today = entertainment_today or []
        self._thirty_day_metric = (
            "engaged" if thirty_day_metric == "engaged" else "effective"
        )

        self._labels["today"] = ["0", "", "2", "", "4", "", "6", "", "8", "", "10", "", "12", "", "14", "", "16", "", "18", "", "20", "", "22", ""]
        self._labels["7d"] = list(self._labels["today"])

        today_date = date.today()
        # Weekday indices for current-week data (Mon=0 to Sun=6)
        days = seven_day_labels or [today_date.strftime("%Y-%m-%d")]
        self._weekday_indices["7d"] = [
            datetime.strptime(d, "%Y-%m-%d").weekday() for d in days
        ]

        # 30-day labels: from 1st of current month to today
        month_start = today_date.replace(day=1)
        days_in_month = (today_date - month_start).days + 1
        markers = []
        for i in range(days_in_month):
            d = month_start + timedelta(days=i)
            # Show day-of-month label, highlight 1st and every 5 days
            if i == 0 or d.day % 5 == 1 or d == today_date:
                markers.append(f"{d.month}/{d.day}")
            else:
                markers.append("")
        self._labels["30d"] = markers
        self._weekday_indices["today"] = []
        self._weekday_indices["30d"] = []

        self._yesterday_work = yesterday_work or []
        self._yesterday_entertainment = yesterday_entertainment or []

        self._apply_series()
        self._update_title()
        self._update_legend()


class _TrendCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._points: list[float | None] = []
        self._labels: list[str] = []
        self._mode = "today"
        self._compare_points: list[float] = []
        self._week_series: list[list[float]] = []
        self._weekday_indices: list[int] = []
        self._work_points: list[float] = []
        self._entertainment_points: list[float] = []
        self._yesterday_work_points: list[float] = []
        self._yesterday_entertainment_points: list[float] = []
        self.setMouseTracking(True)
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
        work_points: list | None = None,
        entertainment_points: list | None = None,
        yesterday_work: list | None = None,
        yesterday_entertainment: list | None = None,
    ) -> None:
        self._week_series = []
        if mode == "7d" and points and isinstance(points[0], (list, tuple)):
            self._week_series = [
                [max(0.0, float(value)) for value in day_points]
                for day_points in points
            ]
            self._points = [max((series[idx] for series in self._week_series), default=0.0) for idx in range(24)]
        else:
            self._points = [
                None if point is None else max(0.0, float(point))
                for point in points
            ]
        self._labels = labels or []
        self._mode = mode
        self._compare_points = [max(0.0, float(p)) for p in (compare_points or [])]
        self._weekday_indices = list(weekday_indices or [])
        self._work_points = [max(0.0, float(p)) for p in (work_points or [])]
        self._entertainment_points = [max(0.0, float(p)) for p in (entertainment_points or [])]
        self._yesterday_work_points = [max(0.0, float(p)) for p in (yesterday_work or [])]
        self._yesterday_entertainment_points = [max(0.0, float(p)) for p in (yesterday_entertainment or [])]
        self.update()

    def _series_state(self) -> str:
        if not self._points:
            return "empty"
        if self._mode == "7d" and self._week_series:
            valid_count = sum(1 for series in self._week_series for value in series if value > 0)
            return "chart" if valid_count > 0 else "empty"
        valid_count = sum(
            1
            for value in self._points
            if value is not None and value > 0
        )
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
            if y_max <= 0:
                return 10.0
            if y_max <= 5:
                return 5.0
            if y_max <= 10:
                return 10.0
            step = 10 if y_max <= 60 else 15 if y_max <= 120 else 30
            return float(((int(y_max) + step - 1) // step) * step)
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

    def _chart_rect(self) -> QRectF:
        """Shared plot bounds for painting and hover hit-testing."""
        return QRectF(self.rect()).adjusted(54, 6, -14, -30)

    def _y_label_rect(self, y: float) -> QRectF:
        return QRectF(0, y - 7, self._chart_rect().left() - 14, 14)

    def _hover_hour_for_x(self, x: float) -> int | None:
        chart = self._chart_rect()
        if not self._points or chart.width() <= 0 or x < chart.left() or x > chart.right():
            return None
        step = chart.width() / max(len(self._points) - 1, 1)
        return max(0, min(23, int((x - chart.left()) / step + 0.5)))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        chart_rect = self._chart_rect()

        state = self._series_state()
        if state == "empty":
            self._draw_empty(painter, r, "暂无趋势数据")
            return
        if state == "accumulating":
            self._draw_empty(painter, r, "📊 数据积累中\n记录满30分钟后开始生成趋势图")
            return

        max_value = max(
            (value for value in self._points if value is not None),
            default=0.0,
        )
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
            painter.drawText(self._y_label_rect(y), Qt.AlignRight | Qt.AlignVCenter, label)

        if self._mode == "7d":
            self._draw_weekday_lines(painter, chart_rect, y_max)
            self._draw_x_axis_labels(painter, chart_rect)
            return

        if self._mode == "today" and self._work_points and self._entertainment_points:
            self._draw_split_lines(painter, chart_rect, y_max)
        else:
            self._draw_single_line(painter, chart_rect, y_max)

        # Yesterday curves (dashed) for work/entertainment comparison
        self._draw_yesterday_lines(painter, chart_rect, y_max)

        self._draw_x_axis_labels(painter, chart_rect)

    def _draw_split_lines(self, painter: QPainter, chart_rect: QRectF, y_max: float) -> None:
        step = chart_rect.width() / max(len(self._points) - 1, 1)

        def _make_points(values: list[float]) -> list[QPointF]:
            pts = []
            for idx, v in enumerate(values):
                x = chart_rect.left() + idx * step
                y = chart_rect.bottom() - (v / y_max) * chart_rect.height()
                pts.append(QPointF(x, y))
            return pts

        ent_pts = _make_points(self._entertainment_points)
        work_pts = _make_points(self._work_points)

        # Entertainment area fill
        if len(ent_pts) > 5:
            fill = QPainterPath()
            fill.moveTo(chart_rect.left(), chart_rect.bottom())
            for pt in ent_pts:
                fill.lineTo(pt)
            fill.lineTo(chart_rect.right(), chart_rect.bottom())
            fill.closeSubpath()
            ent_fill = QColor(COLORS["video_orange"])
            ent_fill.setAlpha(20)
            painter.setBrush(ent_fill)
            painter.setPen(Qt.NoPen)
            painter.drawPath(fill)

        # Entertainment line
        ent_path = QPainterPath()
        ent_path.moveTo(ent_pts[0])
        for pt in ent_pts[1:]:
            ent_path.lineTo(pt)
        painter.setPen(QPen(QColor(COLORS["video_orange"]), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(ent_path)

        # Work area fill
        if len(work_pts) > 5:
            fill = QPainterPath()
            fill.moveTo(chart_rect.left(), chart_rect.bottom())
            for pt in work_pts:
                fill.lineTo(pt)
            fill.lineTo(chart_rect.right(), chart_rect.bottom())
            fill.closeSubpath()
            work_fill = QColor(COLORS["coding_green"])
            work_fill.setAlpha(25)
            painter.setBrush(work_fill)
            painter.setPen(Qt.NoPen)
            painter.drawPath(fill)

        # Work line
        work_path = QPainterPath()
        work_path.moveTo(work_pts[0])
        for pt in work_pts[1:]:
            work_path.lineTo(pt)
        painter.setPen(QPen(QColor(COLORS["coding_green"]), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(work_path)

        # Dots (entertainment)
        dot_ent = QColor(COLORS["video_orange"])
        dot_ent.setAlpha(200)
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot_ent)
        for pt in ent_pts:
            painter.drawEllipse(pt, 2.5, 2.5)

        # Dots (work)
        dot_work = QColor(COLORS["coding_green"])
        dot_work.setAlpha(220)
        painter.setBrush(dot_work)
        for pt in work_pts:
            painter.drawEllipse(pt, 2.5, 2.5)

    def _draw_single_line(self, painter: QPainter, chart_rect: QRectF, y_max: float) -> None:
        step = chart_rect.width() / max(len(self._points) - 1, 1)
        chart_segments = [
            [
                QPointF(
                    chart_rect.left() + index * step,
                    chart_rect.bottom()
                    - (value / y_max) * chart_rect.height(),
                )
                for index, value in segment
            ]
            for segment in self._numeric_segments(self._points)
        ]

        fill_color = QColor(COLORS["success_green"])
        fill_color.setAlpha(25)
        for chart_points in chart_segments:
            if len(chart_points) > 5:
                fill_path = QPainterPath()
                fill_path.moveTo(
                    chart_points[0].x(),
                    chart_rect.bottom(),
                )
                for point in chart_points:
                    fill_path.lineTo(point)
                fill_path.lineTo(
                    chart_points[-1].x(),
                    chart_rect.bottom(),
                )
                fill_path.closeSubpath()
                painter.setBrush(fill_color)
                painter.setPen(Qt.NoPen)
                painter.drawPath(fill_path)

            if len(chart_points) > 1:
                line_path = QPainterPath()
                line_path.moveTo(chart_points[0])
                for point in chart_points[1:]:
                    line_path.lineTo(point)
                painter.setPen(QPen(QColor(COLORS["success_green"]), 2))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(line_path)

        dot_color = QColor(COLORS["success_green"])
        dot_color.setAlpha(220)
        painter.setPen(Qt.NoPen)
        painter.setBrush(dot_color)
        for chart_points in chart_segments:
            for point in chart_points:
                painter.drawEllipse(point, 2.5, 2.5)

    @staticmethod
    def _numeric_segments(
        points: list[float | None],
    ) -> list[list[tuple[int, float]]]:
        segments: list[list[tuple[int, float]]] = []
        current: list[tuple[int, float]] = []
        for index, value in enumerate(points):
            if value is None:
                if current:
                    segments.append(current)
                    current = []
                continue
            current.append((index, value))
        if current:
            segments.append(current)
        return segments

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtWidgets import QToolTip

        if self._mode != "today" or not self._work_points or not self._entertainment_points:
            QToolTip.hideText()
            super().mouseMoveEvent(event)
            return

        chart_rect = self._chart_rect()
        pos = event.position() if hasattr(event, 'position') else event.pos()

        ipos = pos.toPoint()
        if not chart_rect.contains(ipos):
            QToolTip.hideText()
            super().mouseMoveEvent(event)
            return

        hour = self._hover_hour_for_x(pos.x())
        if hour is None:
            QToolTip.hideText()
            super().mouseMoveEvent(event)
            return

        work_m = int(self._work_points[hour]) if hour < len(self._work_points) else 0
        ent_m = int(self._entertainment_points[hour]) if hour < len(self._entertainment_points) else 0
        total_m = work_m + ent_m + max(0, int(self._points[hour]) - work_m - ent_m)
        ratio = int(total_m / 60 * 100) if total_m > 0 else 0

        QToolTip.showText(
            event.globalPos(),
            f"🕒 {hour:02d}:00 - {hour + 1:02d}:00\n"
            f"💼 工作学习: {work_m}分钟\n"
            f"📺 娱乐休闲: {ent_m}分钟\n"
            f"📊 有效占比: {ratio}%",
            self,
        )
        super().mouseMoveEvent(event)

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
            if style.get("dash"):
                pen.setStyle(Qt.DashLine)
                pen.setDashPattern([8, 4])
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

    def _draw_yesterday_lines(self, painter: QPainter, chart_rect: QRectF, y_max: float) -> None:
        """Draw yesterday's work and entertainment as dashed curves for comparison."""
        if self._mode != "today":
            return
        step = chart_rect.width() / max(len(self._points) - 1, 1)

        def _make_points(values: list[float]) -> list[QPointF]:
            pts = []
            for idx, v in enumerate(values):
                x = chart_rect.left() + idx * step
                y = chart_rect.bottom() - (v / y_max) * chart_rect.height()
                pts.append(QPointF(x, y))
            return pts

        # Yesterday work — dashed green
        yw = self._yesterday_work_points
        if yw and sum(yw) > 0:
            yw_pts = _make_points(yw)
            pen = QPen(QColor(COLORS["coding_green"]), 1.5, Qt.DashLine)
            pen.setDashPattern([6, 4])
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            yw_path = QPainterPath()
            yw_path.moveTo(yw_pts[0])
            for pt in yw_pts[1:]:
                yw_path.lineTo(pt)
            painter.drawPath(yw_path)
            # Small hollow dots
            dot_color = QColor(COLORS["coding_green"])
            dot_color.setAlpha(160)
            painter.setPen(Qt.NoPen)
            painter.setBrush(dot_color)
            for pt in yw_pts:
                painter.drawEllipse(pt, 2.0, 2.0)

        # Yesterday entertainment — dashed orange
        ye = self._yesterday_entertainment_points
        if ye and sum(ye) > 0:
            ye_pts = _make_points(ye)
            pen = QPen(QColor(COLORS["video_orange"]), 1.5, Qt.DashLine)
            pen.setDashPattern([6, 4])
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            ye_path = QPainterPath()
            ye_path.moveTo(ye_pts[0])
            for pt in ye_pts[1:]:
                ye_path.lineTo(pt)
            painter.drawPath(ye_path)
            dot_color = QColor(COLORS["video_orange"])
            dot_color.setAlpha(160)
            painter.setPen(Qt.NoPen)
            painter.setBrush(dot_color)
            for pt in ye_pts:
                painter.drawEllipse(pt, 2.0, 2.0)

    def _draw_empty(self, painter: QPainter, rect: QRectF, text: str) -> None:
        painter.setPen(QColor(COLORS["text_muted"]))
        font = painter.font()
        font.setPixelSize(13)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, text)


def _goal_duration(seconds: int | None) -> str:
    parsed = parse_nonnegative_int(seconds) or 0
    hours, remainder = divmod(parsed, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}小时{minutes}分钟"
    if hours:
        return f"{hours}小时"
    return f"{minutes}分钟"


class DailyGoalsCard(QFrame):
    """Compact daily smart target and entertainment boundary card."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setFixedHeight(138)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(7)

        header = QHBoxLayout()
        title = QLabel("今日目标与边界")
        title.setTextFormat(Qt.PlainText)
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {COLORS['text']};"
        )
        header.addWidget(title)
        header.addStretch(1)
        root.addLayout(header)

        (
            work_row,
            self.work_value_label,
            self.work_detail_label,
            self.work_bar,
        ) = self._build_progress_row("工作参与", COLORS["primary"])
        root.addWidget(work_row)
        (
            entertainment_row,
            self.entertainment_value_label,
            self.entertainment_detail_label,
            self.entertainment_bar,
        ) = self._build_progress_row("娱乐边界", COLORS["video_orange"])
        root.addWidget(entertainment_row)

        self.set_data({})

    @staticmethod
    def _build_progress_row(label_text: str, color: str):
        row = QFrame()
        row.setStyleSheet("QFrame { background: transparent; border: none; }")
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(1)
        label = QLabel(label_text)
        value = QLabel("--")
        detail = QLabel("")
        for dynamic in (label, value, detail):
            dynamic.setTextFormat(Qt.PlainText)
        label.setFixedWidth(64)
        label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {COLORS['text']};"
        )
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        value.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {COLORS['text']};"
        )
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet(
            f"QProgressBar {{ background: {COLORS['panel_bg_alt']}; border: none; "
            f"border-radius: 4px; }} QProgressBar::chunk {{ background: {color}; "
            "border-radius: 4px; }}"
        )
        detail.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']};")
        layout.addWidget(label, 0, 0, 2, 1)
        layout.addWidget(value, 0, 1)
        layout.addWidget(bar, 1, 1)
        layout.addWidget(detail, 2, 1)
        return row, value, detail, bar

    def set_data(self, payload: dict | None) -> None:
        data = dict(payload or {})
        if not data:
            self.work_value_label.setText("目标数据积累中")
            self.work_detail_label.setText("")
            self.work_bar.setValue(0)
            self.entertainment_value_label.setText("尚未设置")
            self.entertainment_detail_label.setText("可在设置中心配置")
            self.entertainment_bar.setValue(0)
            return

        work = dict(data.get("work", {}) or {})
        current_work = parse_nonnegative_int(work.get("current_seconds")) or 0
        target = parse_nonnegative_int(work.get("target_seconds"))
        if target:
            self.work_value_label.setText(
                f"{_goal_duration(current_work)} / {_goal_duration(target)}"
            )
            remaining = parse_nonnegative_int(work.get("remaining_seconds")) or 0
            sample_count = parse_nonnegative_int(work.get("sample_count")) or 0
            self.work_detail_label.setText(
                f"还差 {_goal_duration(remaining)} · 参考同类日 {sample_count} 天"
                if remaining
                else f"今日已达成 · 参考同类日 {sample_count} 天"
            )
        else:
            self.work_value_label.setText(f"已参与 {_goal_duration(current_work)}")
            self.work_detail_label.setText("可信同类日不足，暂不生成目标")
        self.work_bar.setValue(
            min(100, parse_nonnegative_int(work.get("progress_percent")) or 0)
        )

        entertainment = dict(data.get("entertainment", {}) or {})
        current_entertainment = (
            parse_nonnegative_int(entertainment.get("current_seconds")) or 0
        )
        limit = parse_nonnegative_int(entertainment.get("limit_seconds"))
        if limit:
            self.entertainment_value_label.setText(
                f"{_goal_duration(current_entertainment)} / {_goal_duration(limit)}"
            )
            state = str(entertainment.get("state", "within"))
            self.entertainment_detail_label.setText(
                "已超过建议边界"
                if state == "over"
                else "接近建议边界"
                if state == "near"
                else "包含前台娱乐与被动视频"
            )
        else:
            self.entertainment_value_label.setText(
                f"已娱乐 {_goal_duration(current_entertainment)}"
            )
            self.entertainment_detail_label.setText("未设置今日边界")
        self.entertainment_bar.setValue(
            min(
                100,
                parse_nonnegative_int(entertainment.get("progress_percent")) or 0,
            )
        )


class _EntertainmentHistoryCanvas(QWidget):
    """Small bar chart / calendar heatmap for entertainment history."""

    day_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._mode = "7d"
        self._points: list[dict] = []
        self._point_states: list[str] = []
        self._bar_duration_labels: list[str] = []
        self._calendar_dates: list[str] = []
        self._over_limit_dates: set[str] = set()
        self._state = "empty"
        self._bar_hit_rects: list[QRectF | None] = []
        self._calendar_hit_rects: list[tuple[QRectF, str, dict | None]] = []
        self._calendar_week_labels: list[str] = []

    def set_data(
        self,
        mode: str,
        points: list[dict] | None,
        date_range: list[str] | tuple[str, str] | None = None,
    ) -> None:
        self._mode = mode if mode in {"7d", "30d"} else "7d"
        raw_points = points if isinstance(points, (list, tuple)) else []
        self._points = sorted(
            [
                dict(point)
                for point in raw_points
                if isinstance(point, dict) and self._valid_date(point.get("date"))
            ],
            key=lambda point: str(point.get("date", "")),
        )
        self._point_states = [self._point_state(point) for point in self._points]
        self._bar_duration_labels = [
            self._bar_duration_label(point) if self._mode == "7d" else ""
            for point in self._points
        ]
        self._bar_hit_rects = [None] * len(self._points)
        self._over_limit_dates = {
            str(point.get("date")) for point in self._points if point.get("over_limit")
        }
        self._calendar_dates = self._calendar_range(date_range)
        self._calendar_week_labels = self._calendar_week_starts(self._calendar_dates)
        self._calendar_hit_rects = []
        self._state = "chart" if self._points else "empty"
        self.setCursor(Qt.PointingHandCursor if self._mode == "7d" and self._points else Qt.ArrowCursor)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        width = self.width() - 8
        x = event.position().x() - 4
        if (event.button() == Qt.LeftButton and self._mode == "7d" and self._points
                and width > 0 and 0 <= x < width):
            index = min(len(self._points) - 1, int(x / width * len(self._points)))
            self.day_activated.emit(str(self._points[index]["date"]))
        super().mousePressEvent(event)

    @staticmethod
    def _point_state(point: dict) -> str:
        if not point.get("has_data", False):
            return "missing"
        if point.get("over_limit", False):
            return "over_limit"
        if (parse_nonnegative_int(point.get("seconds")) or 0) == 0:
            return "zero"
        return "value"

    @staticmethod
    def _bar_duration_label(point: dict) -> str:
        if not point.get("has_data", False):
            return ""
        seconds = parse_nonnegative_int(point.get("seconds")) or 0
        if seconds <= 0:
            return ""
        hours, remainder = divmod(seconds, 3600)
        minutes = remainder // 60
        if hours:
            return f"{hours}h{minutes}m"
        return f"{minutes}m" if minutes else "<1m"

    @staticmethod
    def _bar_colors(point: dict) -> tuple[QColor, QColor | None]:
        if point.get("is_today", False):
            return QColor("#ff8a2b"), QColor("#ffd166")
        if point.get("over_limit", False):
            return QColor("#e66f24"), None
        return QColor(COLORS["video_orange"]), None

    def _tooltip_text_for_index(self, index: int) -> str:
        if not 0 <= index < len(self._points):
            return ""
        context = self._points[index].get("hover_context")
        if not isinstance(context, dict):
            return ""
        label = str(context.get("label", "") or "").strip()
        seconds = parse_nonnegative_int(context.get("seconds")) or 0
        if not label or seconds <= 0:
            return ""
        return f"{label}\n娱乐 {_goal_duration(seconds)}"

    @staticmethod
    def _calendar_week_starts(dates: list[str]) -> list[str]:
        if not dates:
            return []
        first = date.fromisoformat(dates[0])
        week_start = first - timedelta(days=first.weekday())
        weeks = math.ceil((first.weekday() + len(dates)) / 7)
        return [
            f"{(week_start + timedelta(days=7 * index)).month}/{(week_start + timedelta(days=7 * index)).day}"
            for index in range(weeks)
        ]

    @staticmethod
    def _calendar_color(point: dict, maximum: int) -> QColor:
        if not point.get("has_data", False):
            return QColor(COLORS["panel_bg_alt"])
        seconds = parse_nonnegative_int(point.get("seconds")) or 0
        if seconds <= 0:
            return QColor(COLORS["panel_bg_alt"])
        ratio = seconds / max(maximum, 1)
        if ratio <= 0.25:
            return QColor("#854426")
        if ratio <= 0.5:
            return QColor("#a95220")
        if ratio <= 0.75:
            return QColor("#cd6120")
        return QColor(COLORS["video_orange"])

    @staticmethod
    def _calendar_tooltip_text(date_str: str, point: dict | None) -> str:
        try:
            day = date.fromisoformat(date_str)
            heading = f"{day.month}/{day.day} 周{'一二三四五六日'[day.weekday()]}"
        except ValueError:
            return ""
        if not point or not point.get("has_data", False):
            return f"{heading}\n暂无记录"
        seconds = parse_nonnegative_int(point.get("seconds")) or 0
        lines = [heading, f"娱乐 {_goal_duration(seconds)}"]
        context = point.get("hover_context")
        if isinstance(context, dict):
            label = str(context.get("label", "") or "").strip()
            if label:
                lines.append(label)
        return "\n".join(lines)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mode == "7d":
            position = event.position()
            for index, rect in enumerate(self._bar_hit_rects):
                if rect is not None and rect.contains(position):
                    text = self._tooltip_text_for_index(index)
                    if text:
                        QToolTip.showText(event.globalPosition().toPoint(), text, self)
                        return
        elif self._mode == "30d":
            position = event.position()
            for rect, date_str, point in self._calendar_hit_rects:
                if rect.contains(position):
                    QToolTip.showText(
                        event.globalPosition().toPoint(),
                        self._calendar_tooltip_text(date_str, point),
                        self,
                    )
                    return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        QToolTip.hideText()
        super().leaveEvent(event)

    @staticmethod
    def _valid_date(value) -> bool:
        try:
            date.fromisoformat(str(value))
            return True
        except ValueError:
            return False

    def _calendar_range(self, date_range) -> list[str]:
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            try:
                start = date.fromisoformat(str(date_range[0]))
                end = date.fromisoformat(str(date_range[1]))
                if start <= end and (end - start).days < 40:
                    return [
                        (start + timedelta(days=offset)).isoformat()
                        for offset in range((end - start).days + 1)
                    ]
            except ValueError:
                pass
        return [str(point.get("date", "")) for point in self._points]

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._state == "empty":
            painter.setPen(QColor(COLORS["text_muted"]))
            painter.drawText(self.rect(), Qt.AlignCenter, "娱乐数据积累中")
            return
        if self._mode == "30d":
            self._draw_calendar(painter)
        else:
            self._draw_bars(painter)

    def _draw_bars(self, painter: QPainter) -> None:
        rect = QRectF(self.rect()).adjusted(4, 22, -4, -34)
        values = [
            parse_nonnegative_int(point.get("seconds")) or 0
            for point in self._points
            if point.get("has_data", False)
        ]
        maximum = max(values + [1])
        slot = rect.width() / max(len(self._points), 1)
        for index, point in enumerate(self._points):
            x = rect.left() + index * slot
            state = self._point_states[index]
            if state == "missing":
                painter.setPen(QPen(QColor(COLORS["border"]), 1, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(QRectF(x + slot * 0.28, rect.bottom() - 4, slot * 0.44, 3))
            else:
                seconds = parse_nonnegative_int(point.get("seconds")) or 0
                height = max(2.0, seconds / maximum * rect.height())
                color, outline = self._bar_colors(point)
                painter.setPen(QPen(outline, 1.25) if outline is not None else Qt.NoPen)
                painter.setBrush(color)
                bar_rect = QRectF(
                    x + slot * 0.22,
                    rect.bottom() - height,
                    slot * 0.56,
                    height,
                )
                self._bar_hit_rects[index] = bar_rect
                painter.drawRoundedRect(bar_rect, 2, 2)
                duration_label = self._bar_duration_labels[index]
                if duration_label:
                    painter.setPen(QColor(COLORS["text"]))
                    duration_font = painter.font()
                    duration_font.setPixelSize(11)
                    duration_font.setBold(True)
                    painter.setFont(duration_font)
                    painter.drawText(
                        QRectF(x, max(0.0, rect.bottom() - height - 20), slot, 18),
                        Qt.AlignCenter,
                        duration_label,
                    )
            painter.setPen(QColor(COLORS["text_secondary"]))
            font = painter.font()
            font.setPixelSize(11)
            font.setBold(bool(point.get("is_today", False)))
            painter.setFont(font)
            if point.get("is_today", False):
                painter.setPen(QColor(COLORS["text"]))
            label = self._short_date(str(point.get("date", "")), bool(point.get("is_today")))
            painter.drawText(QRectF(x, rect.bottom() + 8, slot, 18), Qt.AlignCenter, label)

    def _draw_calendar(self, painter: QPainter) -> None:
        rect = QRectF(self.rect()).adjusted(26, 22, -4, -4)
        self._calendar_hit_rects = []
        point_map = {str(point.get("date", "")): point for point in self._points}
        dates = self._calendar_dates
        if not dates:
            return
        first = date.fromisoformat(dates[0])
        weeks = max(1, math.ceil((first.weekday() + len(dates)) / 7))
        cell_w = rect.width() / weeks
        cell_h = rect.height() / 7
        maximum = max(
            [parse_nonnegative_int(point.get("seconds")) or 0 for point in self._points] + [1]
        )
        painter.setPen(QColor(COLORS["text_secondary"]))
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        for column, label in enumerate(self._calendar_week_labels):
            painter.drawText(
                QRectF(rect.left() + column * cell_w, 1, cell_w, 18),
                Qt.AlignCenter,
                label,
            )
        for weekday, text in enumerate("一二三四五六日"):
            painter.drawText(QRectF(0, rect.top() + weekday * cell_h, 20, cell_h), Qt.AlignCenter, text)
        for index, date_str in enumerate(dates):
            day = date.fromisoformat(date_str)
            offset = first.weekday() + index
            column, row = divmod(offset, 7)
            cell = QRectF(
                rect.left() + column * cell_w + 1,
                rect.top() + row * cell_h + 1,
                max(3.0, cell_w - 3),
                max(3.0, cell_h - 3),
            )
            point = point_map.get(date_str)
            if point is None or not point.get("has_data", False):
                painter.setPen(QPen(QColor(COLORS["border"]), 1))
                painter.setBrush(self._calendar_color(point or {}, maximum))
            else:
                outline = QColor("#ffd166") if point.get("is_today", False) else None
                painter.setPen(QPen(outline, 1.25) if outline is not None else Qt.NoPen)
                painter.setBrush(self._calendar_color(point, maximum))
            painter.drawRoundedRect(cell, 2, 2)
            self._calendar_hit_rects.append((cell, date_str, point))
            if point and point.get("over_limit", False):
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#e66f24"))
                triangle = QPainterPath()
                triangle.moveTo(cell.right() - 6, cell.top())
                triangle.lineTo(cell.right(), cell.top())
                triangle.lineTo(cell.right(), cell.top() + 6)
                triangle.closeSubpath()
                painter.drawPath(triangle)

    @staticmethod
    def _short_date(value: str, is_today: bool) -> str:
        if is_today:
            return "今日"
        try:
            return f"{date.fromisoformat(value).month}/{date.fromisoformat(value).day}"
        except ValueError:
            return value


class EntertainmentHistoryCard(QFrame):
    """Entertainment history card backed by the dashboard snapshot model."""

    day_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._mode = "7d"
        self._history: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 10, 16, 10)
        root.setSpacing(6)
        header = QHBoxLayout()
        self._title_label = QLabel("娱乐时间 · 近7天")
        self._title_label.setTextFormat(Qt.PlainText)
        self._title_label.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {COLORS['text']};")
        header.addWidget(self._title_label)
        header.addStretch(1)
        self._mode_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for mode, text in (("7d", "近7天"), ("30d", "近30天")):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ padding: 3px 8px; border-radius: 6px; border: 1px solid {COLORS['border']}; color: {COLORS['text_secondary']}; background: {COLORS['panel_bg_alt']}; font-size: 11px; }}"
                f"QPushButton:checked {{ background: {COLORS['video_orange']}; color: white; border-color: {COLORS['video_orange']}; }}"
            )
            button.clicked.connect(lambda _checked=False, current=mode: self.set_mode(current))
            group.addButton(button)
            self._mode_buttons[mode] = button
            header.addWidget(button)
        self._mode_buttons["7d"].setChecked(True)
        root.addLayout(header)

        details = QHBoxLayout()
        details.setSpacing(6)
        self._range_label = QLabel("")
        self._range_label.setTextFormat(Qt.PlainText)
        self._range_label.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {COLORS['text_secondary']};")
        details.addWidget(self._range_label)
        self._captured_label = QLabel("")
        self._captured_label.setTextFormat(Qt.PlainText)
        self._captured_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_secondary']};")
        details.addWidget(self._captured_label)
        details.addStretch(1)
        root.addLayout(details)
        self.canvas = _EntertainmentHistoryCanvas()
        self.canvas.day_activated.connect(self.day_activated.emit)
        self.canvas.setMinimumHeight(110)
        root.addWidget(self.canvas, 1)
        summaries = QHBoxLayout()
        summaries.setSpacing(8)
        self._summary_labels: list[tuple[QLabel, QLabel]] = []
        self._summary_cells: list[MetricCell] = []
        for title in ("日均时长", "最高一天", "总时长"):
            cell = HistoryMetricCell(title)
            label, value = cell.label, cell.value
            summaries.addWidget(cell, 1)
            self._summary_labels.append((label, value))
            self._summary_cells.append(cell)
        root.addLayout(summaries)
        self._status_label = QLabel("娱乐数据积累中")
        self._status_label.setTextFormat(Qt.PlainText)
        self._status_label.setVisible(False)
        self._status_label.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']};"
        )
        root.addWidget(self._status_label)
        self.set_data({})

    def _dynamic_labels(self) -> list[QLabel]:
        return [self._title_label, self._range_label, self._captured_label, self._status_label] + [label for cell in self._summary_cells for label in (cell.label, cell.value, cell.detail)]

    def set_data(self, payload: dict | None) -> None:
        data = dict(payload or {}).get("entertainment_history")
        self._history = dict(data) if isinstance(data, dict) else {}
        self._apply_mode()

    def set_mode(self, mode: str) -> None:
        if mode not in {"7d", "30d"}:
            return
        self._mode = mode
        if not self._mode_buttons[mode].isChecked():
            self._mode_buttons[mode].setChecked(True)
        self._apply_mode()

    def _apply_mode(self) -> None:
        label = "近7天" if self._mode == "7d" else "近30天"
        self._title_label.setText(f"娱乐时间 · {label}")
        self.canvas.setMinimumHeight(110 if self._mode == "7d" else 126)
        status = self._history.get("status", {})
        status = dict(status) if isinstance(status, dict) else {"kind": str(status)}
        unavailable = status.get("kind") == "unavailable"
        if not self._history or unavailable:
            self._status_label.setText("暂不可用" if unavailable else "娱乐数据积累中")
            self._status_label.setVisible(True)
            self._range_label.setText("")
            self._captured_label.setText("")
            self.canvas.set_data(self._mode, [])
            self._set_summary({})
            return
        self._status_label.setVisible(False)
        self._captured_label.setText(self._captured_text(self._history.get("captured_at")))
        raw_mode_data = self._history.get("week" if self._mode == "7d" else "month", {})
        mode_data = dict(raw_mode_data) if isinstance(raw_mode_data, dict) else {}
        self._range_label.setText(self._range_text(mode_data.get("date_range")))
        if not mode_data.get("points"):
            self._status_label.setText("娱乐数据积累中")
            self._status_label.setVisible(True)
        self.canvas.set_data(self._mode, mode_data.get("points", []), mode_data.get("date_range"))
        raw_summary = mode_data.get("summary", {})
        self._set_summary(dict(raw_summary) if isinstance(raw_summary, dict) else {})

    def _set_summary(self, summary: dict) -> None:
        total = parse_nonnegative_int(summary.get("total_seconds"))
        average = parse_nonnegative_int(summary.get("average_seconds"))
        maximum = parse_nonnegative_int(summary.get("max_seconds"))
        max_date = summary.get("max_date")
        self._summary_cells[0].set_values(
            label="日均时长",
            value=_goal_duration(average) if average is not None else "--",
        )
        self._summary_cells[1].set_values(
            label="最高一天",
            value=self._short_date(str(max_date)) if max_date and maximum is not None else "--",
            detail=_goal_duration(maximum) if max_date and maximum is not None else "",
        )
        self._summary_cells[2].set_values(
            label="总时长",
            value=_goal_duration(total) if total is not None else "--",
        )

    @staticmethod
    def _captured_text(value) -> str:
        return history_captured_text(value)

    @staticmethod
    def _range_text(value) -> str:
        return history_range_text(value)

    @staticmethod
    def _short_date(value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
            return f"{parsed.month}/{parsed.day}"
        except ValueError:
            return value


class TopAppListWidget(QFrame):
    MAX_ROWS = 5
    activated = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._row_widgets: list[QWidget] = []
        self.setCursor(Qt.PointingHandCursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 14)
        root.setSpacing(10)

        title = QLabel("软件使用排行榜")
        title.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {COLORS['text']};")
        root.addWidget(title)

        self.rows_container = QVBoxLayout()
        self.rows_container.setSpacing(8)
        root.addLayout(self.rows_container)
        root.addStretch()

    def _build_row(self, rank: int):
        row = QWidget()
        row.setFixedHeight(30)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        rank_label = QLabel(str(rank))
        rank_label.setFixedWidth(18)
        rank_label.setStyleSheet(f"font-size: 15px; color: {COLORS['text_secondary']}; font-weight: 700;")
        layout.addWidget(rank_label)

        icon_label = QLabel("")
        icon_label.setFixedSize(28, 28)
        icon_label.setStyleSheet(f"background: {COLORS['panel_bg_alt']}; border-radius: 6px;")
        layout.addWidget(icon_label)

        name_label = ElidedLabel("--")
        name_label.setMinimumWidth(96)
        name_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text']}; font-weight: 600;")
        layout.addWidget(name_label)

        progress_bar = QProgressBar()
        progress_bar.setTextVisible(False)
        progress_bar.setRange(0, 100)
        progress_bar.setFixedHeight(10)
        progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background: {COLORS['panel_bg_alt']};
                border: none;
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background: {COLORS['primary']};
                border-radius: 5px;
            }}
            """
        )
        layout.addWidget(progress_bar, 1)

        duration_label = QLabel("--")
        duration_label.setTextFormat(Qt.PlainText)
        duration_label.setFixedWidth(68)
        duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        duration_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        layout.addWidget(duration_label)

        return row, icon_label, name_label, progress_bar, duration_label

    def set_items(self, items) -> None:
        # Remove old rows
        for w in self._row_widgets:
            self.rows_container.removeWidget(w)
            w.deleteLater()
        self._row_widgets.clear()

        n = min(len(items), self.MAX_ROWS)
        if n == 0:
            return

        normalized = []
        for item in items[:n]:
            if isinstance(item, dict):
                normalized.append(dict(item))
            else:
                process_name, display_name, seconds, icon = item
                normalized.append(
                    {
                        "process_name": process_name,
                        "display_name": display_name,
                        "seconds": seconds,
                        "engaged_seconds": 0,
                        "passive_seconds": 0,
                        "purpose": "",
                        "icon": icon,
                    }
                )
        max_seconds = max((int(item.get("seconds", 0) or 0) for item in normalized), default=1)
        for index in range(n):
            item = normalized[index]
            process_name = str(item.get("process_name", "") or "")
            display_name = str(item.get("display_name", "") or process_name)
            seconds = int(item.get("seconds", 0) or 0)
            icon = item.get("icon")
            row, icon_lbl, name_lbl, bar, dur_lbl = self._build_row(index + 1)
            icon_lbl.setPixmap(icon.pixmap(26, 26) if icon else QIcon().pixmap(18, 18))
            name_lbl.setText(display_name)
            if not name_lbl.toolTip() and display_name != process_name:
                name_lbl.setToolTip(f"{display_name} — {process_name}")
            bar.setValue(int(round((seconds / max_seconds) * 100)))
            dur_lbl.setText(fmt_seconds(seconds))
            self.rows_container.addWidget(row)
            self._row_widgets.append(row)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.activated.emit()
        super().mouseReleaseEvent(event)


class WorkInterruptionCard(QFrame):
    """Compact, evidence-based summary of interruptions between work blocks."""

    _SOURCE_COLORS = {
        "social": COLORS["social_purple"],
        "entertainment": COLORS["video_orange"],
        "idle": COLORS["idle_gray"],
        "browser": COLORS["tools_cyan"],
        "other": COLORS["text_muted"],
    }

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("workInterruptionCard")
        self.setStyleSheet(
            f"QFrame#workInterruptionCard {{ background: {COLORS['panel_bg_alt']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 9px; }}"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._source_rows: list[QFrame] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(5)
        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("工作切换")
        title.setTextFormat(Qt.PlainText)
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 800; color: {COLORS['text']}; border: none;"
        )
        header.addWidget(title)
        header.addStretch()
        badge = QLabel("今日")
        badge.setTextFormat(Qt.PlainText)
        badge.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {COLORS['primary']}; "
            f"background: {COLORS['card_bg_alt']}; border: none; border-radius: 8px; padding: 3px 8px;"
        )
        header.addWidget(badge)
        layout.addLayout(header)
        self.conclusion_label = QLabel()
        self.conclusion_label.setObjectName("interruptionConclusion")
        self.conclusion_label.setTextFormat(Qt.PlainText)
        self.conclusion_label.setStyleSheet(
            f"font-size: 17px; font-weight: 800; color: {COLORS['text']}; border: none;"
        )
        layout.addWidget(self.conclusion_label)

        metrics = QHBoxLayout()
        metrics.setSpacing(7)
        self.count_value = self._add_metric(metrics, "明显切换")
        self.duration_value = self._add_metric(metrics, "切换累计")
        self.primary_value = self._add_metric(metrics, "主要来源")
        layout.addLayout(metrics)

        self.source_layout = QVBoxLayout()
        self.source_layout.setContentsMargins(0, 0, 0, 0)
        self.source_layout.setSpacing(3)
        layout.addLayout(self.source_layout)
        self.set_data({"status": "empty"})

    def _add_metric(self, layout: QHBoxLayout, label_text: str) -> QLabel:
        metric = QFrame()
        metric.setStyleSheet(
            f"background: {COLORS['card_bg_alt']}; border: none; border-radius: 6px;"
        )
        metric_layout = QVBoxLayout(metric)
        metric_layout.setContentsMargins(8, 4, 8, 4)
        metric_layout.setSpacing(0)
        label = QLabel(label_text)
        label.setTextFormat(Qt.PlainText)
        label.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {COLORS['text_secondary']}; border: none;"
        )
        value = QLabel("--")
        value.setTextFormat(Qt.PlainText)
        value.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {COLORS['text']}; border: none;"
        )
        metric_layout.addWidget(label)
        metric_layout.addWidget(value)
        layout.addWidget(metric, 1)
        return value

    def _clear_source_rows(self) -> None:
        for row in self._source_rows:
            self.source_layout.removeWidget(row)
            row.deleteLater()
        self._source_rows.clear()

    def set_data(self, data: dict | None) -> None:
        payload = dict(data or {})
        status = str(payload.get("status", "empty") or "empty")
        self._clear_source_rows()
        if status == "unavailable":
            self.conclusion_label.setText("切换数据暂不可用，稍后会自动恢复")
            self.count_value.setText("--")
            self.duration_value.setText("--")
            self.primary_value.setText("--")
            self.setFixedHeight(106)
            return
        if status != "ready":
            self.conclusion_label.setText("今天暂未识别到明显的工作切换")
            self.count_value.setText("0次")
            self.duration_value.setText("0分钟")
            self.primary_value.setText("--")
            self.setFixedHeight(106)
            return

        count = parse_nonnegative_int(payload.get("total_count")) or 0
        seconds = parse_nonnegative_int(payload.get("total_seconds")) or 0
        primary = dict(payload.get("primary_source", {}) or {})
        primary_label = str(primary.get("label", "其他应用") or "其他应用")
        self.conclusion_label.setText(f"今天切换工作 {count} 次，主要去向 {primary_label}")
        self.count_value.setText(f"{count}次")
        self.duration_value.setText(_goal_duration(seconds))
        self.primary_value.setText(primary_label)

        for source in list(payload.get("sources", []) or [])[:3]:
            self._add_source_row(dict(source or {}))
        self.setFixedHeight(106 + len(self._source_rows) * 24)

    def _add_source_row(self, source: dict) -> None:
        kind = str(source.get("kind", "other") or "other")
        color = self._SOURCE_COLORS.get(kind, self._SOURCE_COLORS["other"])
        row = QFrame()
        row.setStyleSheet("background: transparent; border: none;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 0, 2, 0)
        row_layout.setSpacing(6)
        dot = QLabel("●")
        dot.setTextFormat(Qt.PlainText)
        dot.setStyleSheet(f"font-size: 10px; color: {color}; border: none;")
        row_layout.addWidget(dot)
        label = ElidedLabel(str(source.get("label", "其他应用") or "其他应用"))
        label.setObjectName("interruptionSourceLabel")
        label.setTextFormat(Qt.PlainText)
        label.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {COLORS['text']}; border: none;"
        )
        row_layout.addWidget(label, 1)
        count = parse_nonnegative_int(source.get("count")) or 0
        seconds = parse_nonnegative_int(source.get("seconds")) or 0
        value = QLabel(f"{count}次 · {_goal_duration(seconds)}")
        value.setTextFormat(Qt.PlainText)
        value.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_secondary']}; border: none;"
        )
        row_layout.addWidget(value)
        self.source_layout.addWidget(row)
        self._source_rows.append(row)


class WorkEpisodeListWidget(QFrame):
    """Compact list of coherent work episodes rather than raw sessions."""

    MAX_ROWS = 5
    MIN_DISPLAY_SECONDS = 5 * 60
    ROW_HEIGHT = 72
    ROW_SPACING = 6
    EMPTY_HEIGHT = 34

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("workEpisodeList")
        self.setStyleSheet("QFrame#workEpisodeList { background: transparent; border: none; }")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._episodes: list[dict] = []
        self._row_widgets: list[QWidget] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.ROW_SPACING)

    def _set_content_height(self, row_count: int) -> None:
        if row_count <= 0:
            self.setFixedHeight(self.EMPTY_HEIGHT)
            return
        visible_rows = min(row_count, self.MAX_ROWS)
        self.setFixedHeight(
            visible_rows * self.ROW_HEIGHT
            + max(0, visible_rows - 1) * self.ROW_SPACING
        )

    def set_episodes(self, episodes: list[dict]) -> None:
        for row in self._row_widgets:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._row_widgets.clear()
        # The focus card is meant to surface substantial work blocks, not
        # every short context switch.  This is display-only: the snapshot and
        # persisted sessions still retain all episode data for reports.
        filtered: list[dict] = []
        for episode in episodes or []:
            seconds = (
                parse_nonnegative_int(episode.get("seconds"))
                if "seconds" in episode
                else parse_nonnegative_int(episode.get("engaged_seconds"))
            )
            if seconds is not None and seconds > self.MIN_DISPLAY_SECONDS:
                filtered.append(episode)
        self._episodes = filtered
        if not self._episodes:
            empty = QLabel("暂无可回顾的工作片段")
            empty.setTextFormat(Qt.PlainText)
            empty.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']}; padding: 8px 0;")
            self._layout.addWidget(empty)
            self._row_widgets.append(empty)
            self._set_content_height(0)
            return
        for episode in self._episodes[: self.MAX_ROWS]:
            row = self._build_row(episode)
            self._layout.addWidget(row)
            self._row_widgets.append(row)
        self._set_content_height(len(self._row_widgets))

    def _build_row(self, episode: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("workEpisodeRow")
        row.setFixedHeight(self.ROW_HEIGHT)
        row.setStyleSheet(
            f"QFrame#workEpisodeRow {{ background: {COLORS['panel_bg_alt']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 8px; }} "
            f"QFrame#workEpisodeRow:hover {{ background: {COLORS['card_bg_alt']}; }}"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 7, 12, 7)
        layout.setSpacing(10)

        accent = QFrame()
        accent.setObjectName("workEpisodeAccent")
        accent.setFixedWidth(3)
        accent.setStyleSheet(
            f"QFrame#workEpisodeAccent {{ background: {COLORS['coding_green']}; "
            "border: none; border-radius: 1px; }"
        )
        layout.addWidget(accent)

        text_box = QWidget()
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        topic_text = str(episode.get("topic", "") or "未命名工作片段")
        topic = ElidedLabel(topic_text)
        topic.setObjectName("workEpisodeTopic")
        topic.setTextFormat(Qt.PlainText)
        topic.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {COLORS['text']};")
        app_names = [
            str(app).strip()
            for app in episode.get("apps", [])
            if str(app).strip()
        ]
        apps_text = " / ".join(app_names)
        app_label = ElidedLabel(apps_text)
        app_label.setObjectName("workEpisodeApps")
        app_label.setTextFormat(Qt.PlainText)
        app_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_secondary']};")
        duplicate_single_app = (
            len(app_names) == 1
            and app_names[0].casefold() == topic_text.strip().casefold()
        )
        text_layout.addWidget(topic)
        text_layout.addWidget(app_label)
        # QLayout reparents the label to text_box. Change visibility only
        # afterwards, otherwise Qt briefly treats the parentless label as a
        # standalone window during each dashboard refresh.
        app_label.setVisible(bool(apps_text) and not duplicate_single_app)
        layout.addWidget(text_box, 1)

        meta_box = QWidget()
        meta_layout = QVBoxLayout(meta_box)
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(2)
        start = str(episode.get("start_time", "") or "")
        end = str(episode.get("end_time", "") or "")
        time_label = QLabel(f"{start[11:16]}–{end[11:16]}")
        time_label.setObjectName("workEpisodeTime")
        time_label.setTextFormat(Qt.PlainText)
        time_label.setAlignment(Qt.AlignRight)
        time_label.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {COLORS['primary_hover']};"
        )
        seconds = (
            parse_nonnegative_int(episode.get("seconds"))
            if "seconds" in episode
            else parse_nonnegative_int(episode.get("engaged_seconds"))
        ) or 0
        metric_label = str(episode.get("metric_label", "参与") or "参与")
        duration_label = QLabel(f"{metric_label} {fmt_seconds(seconds)}")
        duration_label.setObjectName("workEpisodeDuration")
        duration_label.setTextFormat(Qt.PlainText)
        duration_label.setAlignment(Qt.AlignRight)
        duration_label.setStyleSheet(f"font-size: 12px; font-weight: 800; color: {COLORS['primary']};")
        meta_layout.addWidget(time_label)
        meta_layout.addWidget(duration_label)
        layout.addWidget(meta_box)
        return row


class DistributionLegend(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # The legend is redrawn while the main window is being restored and
        # resized.  Keep its child surfaces transparent so the global QWidget
        # background cannot flash through the card's backing store.
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self._rows: list[QWidget] = []
        self._row_parts: list[dict[str, QWidget]] = []
        self._items_signature: tuple[tuple[tuple[str, int, str], ...], int] | None = None

    def set_items(self, items: list[tuple[str, int, str]], total_seconds: int) -> None:
        total = max(1, total_seconds)
        normalized = tuple(
            (str(name), max(0, int(seconds)), str(color))
            for name, seconds, color in items
        )
        signature = (normalized, total)
        if signature == self._items_signature:
            return
        self._items_signature = signature

        # Batch structural changes.  In particular, do not expose the empty
        # intermediate layout while the window is being restored from the
        # taskbar or rapidly resized.
        self.setUpdatesEnabled(False)
        try:
            while len(self._rows) > len(normalized):
                row = self._rows.pop()
                self._row_parts.pop()
                self.layout.removeWidget(row)
                row.deleteLater()

            while len(self._rows) < len(normalized):
                row, parts = self._build_row()
                self.layout.addWidget(row)
                self._rows.append(row)
                self._row_parts.append(parts)

            for parts, (name, seconds, color) in zip(self._row_parts, normalized):
                self._update_row(parts, name, seconds, color, total)
            # Font/DPI and duration length determine the space needed; use one
            # common width so every row's duration and percentage stay aligned.
            for parts in self._row_parts:
                parts['time'].ensurePolished()
                parts['pct'].ensurePolished()
            time_width = max((
                parts['time'].fontMetrics().horizontalAdvance(parts['time'].text()) + 12
                for parts in self._row_parts
            ), default=60)
            for parts in self._row_parts:
                parts['time'].setFixedWidth(max(60, time_width))
                pct = parts['pct']
                pct.setFixedWidth(max(36, pct.fontMetrics().horizontalAdvance(pct.text()) + 8))
        finally:
            self.setUpdatesEnabled(True)
            self.update()

    def _build_row(self) -> tuple[QWidget, dict[str, QWidget]]:
        row = QWidget()
        row.setAttribute(Qt.WA_TranslucentBackground)
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        icon = QLabel("●")
        icon.setFixedWidth(16)
        row_layout.addWidget(icon)

        name_label = ElidedLabel()
        name_label.setMinimumWidth(72)
        row_layout.addWidget(name_label)

        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setFixedHeight(8)
        bar.setFocusPolicy(Qt.NoFocus)
        bar.setProperty("_daylens_distribution_color", "")
        row_layout.addWidget(bar, 1)

        time_label = QLabel()
        time_label.setFixedWidth(60)
        time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_layout.addWidget(time_label)

        pct_label = QLabel()
        pct_label.setFixedWidth(36)
        pct_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_layout.addWidget(pct_label)

        return row, {
            "icon": icon,
            "name": name_label,
            "bar": bar,
            "time": time_label,
            "pct": pct_label,
        }

    @staticmethod
    def _update_row(
        parts: dict[str, QWidget],
        name: str,
        seconds: int,
        color: str,
        total: int,
    ) -> None:
        pct = int(round(seconds / total * 100))
        icon = parts["icon"]
        icon.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: 700;")
        name_label = parts["name"]
        name_label.setText(name)
        name_label.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {COLORS['text']};"
        )
        bar = parts["bar"]
        bar.setValue(pct)
        if bar.property("_daylens_distribution_color") != color:
            bar.setStyleSheet(f"""
                QProgressBar {{
                    background: {COLORS['panel_bg_alt']};
                    border: none;
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background: {color};
                    border-radius: 4px;
                }}
            """)
            bar.setProperty("_daylens_distribution_color", color)
        time_label = parts["time"]
        time_label.setText(fmt_seconds(seconds))
        time_label.setStyleSheet(
            f"font-size: 14px; color: {COLORS['text']}; font-weight: 700;"
        )
        pct_label = parts["pct"]
        pct_label.setText(f"{pct}%")
        pct_label.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']}; font-weight: 600;"
        )


def _timeline_duration_text(session: dict) -> str:
    seconds = (
        session.get("effective_seconds", 0)
        or session.get("idle_seconds", 0)
        or session.get("duration_seconds", 0)
        or 0
    )
    return fmt_seconds(seconds)
