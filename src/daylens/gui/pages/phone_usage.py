"""Read-only daily and rolling iPhone App usage rankings."""

from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...services import phone_usage
from ...utils import fmt_seconds
from .. import style as ui_style


class PhoneUsagePage(QWidget):
    refresh_requested = Signal()
    receiver_settings_requested = Signal()

    def __init__(self, archive: Path):
        super().__init__()
        self._archive = archive
        self._active = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("手机 App 使用时长")
        title.setStyleSheet(ui_style.get_section_title())
        layout.addWidget(title)

        controls = QHBoxLayout()
        self.period = QComboBox()
        self.period.setAccessibleName("统计范围")
        for label, days in (("单日", 1), ("近 7 天", 7), ("近 30 天", 30)):
            self.period.addItem(label, days)
        self.day = QComboBox()
        self.day.setAccessibleName("数据日期")
        self.day.setPlaceholderText("暂无日期")
        self.day.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.day.setMinimumContentsLength(len("YYYY-MM-DD"))
        self.day.view().setTextElideMode(Qt.ElideNone)
        self.day.setEnabled(False)
        refresh = QPushButton("刷新")
        refresh.setStyleSheet(ui_style.get_button_secondary_style())
        controls.addWidget(self.period)
        controls.addWidget(self.day)
        controls.addWidget(refresh)
        controls.addStretch()
        receiver_settings = QPushButton("Windows 接收端")
        receiver_settings.setStyleSheet(ui_style.get_button_secondary_style())
        receiver_settings.clicked.connect(self.receiver_settings_requested)
        controls.addWidget(receiver_settings)
        layout.addLayout(controls)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {ui_style.COLORS['text_secondary']};")
        layout.addWidget(self.status)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["排名", "App", "累计时长"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(ui_style.get_table_style())
        layout.addWidget(self.table, 1)

        self.period.currentIndexChanged.connect(self.refresh)
        self.day.currentIndexChanged.connect(lambda: self._show_usage(update_dates=False))
        refresh.clicked.connect(self.refresh)
        refresh.clicked.connect(self.refresh_requested)

    def activate(self, force: bool = False) -> None:
        self._active = True
        self.refresh()

    def deactivate(self) -> None:
        self._active = False

    def archive_changed(self) -> None:
        if self._active:
            self.refresh()

    def refresh(self) -> None:
        self._show_usage(update_dates=True)

    def _set_available_dates(self, dates: list[date]) -> None:
        selected = self.day.currentText()
        with QSignalBlocker(self.day):
            self.day.clear()
            self.day.addItems([day.isoformat() for day in dates])
            self.day.setCurrentIndex(max(0, self.day.findText(selected)) if dates else -1)
        self.day.setEnabled(bool(dates))

    def _show_usage(self, *, update_dates: bool) -> None:
        days = self.period.currentData()
        self.day.setVisible(days == 1)
        self.table.setRowCount(0)
        try:
            if not self._archive.is_dir():
                self._set_available_dates([])
                self.status.setText("暂无本地手机使用记录。")
                return
            today = date.today()
            if days == 1:
                if update_dates:
                    self._set_available_dates(phone_usage.available_phone_days(self._archive, today))
                if self.day.currentIndex() < 0:
                    self.status.setText("暂无可查看的手机使用记录。")
                    return
                end = date.fromisoformat(self.day.currentText())
            else:
                end = today - timedelta(days=1)
            start = end - timedelta(days=days - 1)
            usage = phone_usage.load_phone_usage(self._archive, start, end)
        except (OSError, RuntimeError):
            self._set_available_dates([])
            self.status.setText("无法读取本地手机使用记录。")
            return
        if days == 1 and not usage.received_days and not update_dates:
            self.refresh()
            return

        period_text = end.isoformat() if days == 1 else f"{start.isoformat()} 至 {end.isoformat()}"
        details = [period_text, f"已收到 {usage.received_days}/{days} 天"]
        if usage.snapshot_days:
            details.append(f"其中 {usage.snapshot_days} 天为当日快照")
        if usage.unreadable_days:
            details.append(f"{usage.unreadable_days} 天无法读取")
        self.status.setText("  ·  ".join(details))
        self.table.setRowCount(len(usage.apps))
        for row, (name, seconds) in enumerate(usage.apps):
            rank = QTableWidgetItem(str(row + 1))
            rank.setTextAlignment(Qt.AlignCenter)
            duration_text = fmt_seconds(seconds)
            if seconds >= 3600 and seconds % 60:
                duration_text += f"{seconds % 60}秒"
            duration = QTableWidgetItem(duration_text)
            duration.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 0, rank)
            self.table.setItem(row, 1, QTableWidgetItem(name))
            self.table.setItem(row, 2, duration)
