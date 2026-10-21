"""Small shared presentation primitives used by dashboard cards and page shells."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import style as ui_style


class PageHeader(QWidget):
    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setTextFormat(Qt.PlainText)
        self.title_label.setStyleSheet(
            f"font-size: 18px; font-weight: 900; color: {ui_style.COLORS['text']};"
        )
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setTextFormat(Qt.PlainText)
        self.subtitle_label.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};"
        )
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)

    def set_text(self, title: str, subtitle: str = "") -> None:
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))


class CardHeader(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(title)
        self.title_label.setTextFormat(Qt.PlainText)
        self.title_label.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {ui_style.COLORS['text']};"
        )
        layout.addWidget(self.title_label)
        layout.addStretch(1)


class DurationLabel(QLabel):
    def __init__(self, text: str = "--", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {ui_style.COLORS['text']};"
        )


class StatusBadge(QLabel):
    def __init__(self, text: str = "", kind: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setAlignment(Qt.AlignCenter)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        colors = {
            "success": ui_style.COLORS["success_green"],
            "warning": ui_style.COLORS["warning_yellow"],
            "error": ui_style.COLORS["danger_red"],
            "primary": ui_style.COLORS["primary"],
            "neutral": ui_style.COLORS["text_secondary"],
        }
        color = colors.get(kind, colors["neutral"])
        self.setStyleSheet(
            f"font-size: 12px; font-weight: 800; color: {color}; "
            f"background: {ui_style.COLORS['panel_bg_alt']}; "
            f"border: 1px solid {ui_style.COLORS['border']}; border-radius: 8px; padding: 3px 8px;"
        )


class MetricCell(QFrame):
    def __init__(self, label: str = "", value: str = "--", detail: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: {ui_style.COLORS['panel_bg_alt']}; border-radius: 7px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(1)
        self.label = QLabel(label)
        self.value = DurationLabel(value)
        self.detail = QLabel(detail)
        for item in (self.label, self.detail):
            item.setTextFormat(Qt.PlainText)
        self.label.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};"
        )
        self.detail.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']};"
        )
        self.detail.setVisible(bool(detail))
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_values(self, *, label: str, value: str, detail: str = "") -> None:
        self.label.setText(label)
        self.value.setText(value)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))


class EmptyState(QLabel):
    def __init__(self, text: str = "尚无记录", parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"font-size: 13px; color: {ui_style.COLORS['text_muted']}; padding: 10px;"
        )


class ErrorState(EmptyState):
    def __init__(self, text: str = "读取失败，已保留上次数据", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            f"font-size: 13px; color: {ui_style.COLORS['danger_red']}; padding: 10px;"
        )
