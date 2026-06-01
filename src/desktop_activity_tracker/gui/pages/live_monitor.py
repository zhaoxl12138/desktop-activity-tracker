"""Live monitor page - current window info + recent sample history."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt

from ..style import COLORS, TABLE_STYLE, get_category_color


class LiveMonitorPage(QWidget):
    def __init__(self):
        super().__init__()
        self._samples = []  # last 20 samples

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("实时监控")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        # Current window info
        info_frame = QFrame()
        info_frame.setStyleSheet("background: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 8px; padding: 16px;")
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(8)

        self.lbl_process = QLabel("进程: --")
        self.lbl_title = QLabel("标题: --")
        self.lbl_category = QLabel("分类: --")
        self.lbl_status = QLabel("状态: --")
        for lbl in [self.lbl_process, self.lbl_title, self.lbl_category, self.lbl_status]:
            lbl.setStyleSheet("font-size: 13px; color: #2C3E50;")
            info_layout.addWidget(lbl)
        layout.addWidget(info_frame)

        # History table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["时间", "进程", "分类", "有效"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet(TABLE_STYLE)
        layout.addWidget(self.table)

    def on_sample_updated(self, sample):
        self._samples.insert(0, sample)
        if len(self._samples) > 20:
            self._samples = self._samples[:20]

        # Update current info
        self.lbl_process.setText(f"进程: {sample.get('process_name', '--')}")
        self.lbl_title.setText(f"标题: {sample.get('window_title', '--')[:80]}")
        color = get_category_color(sample.get("category_key", "other"))
        self.lbl_category.setText(f"分类: {sample.get('category_name', '--')}")
        self.lbl_category.setStyleSheet(f"font-size: 13px; color: {color}; font-weight: bold;")
        status = "有效" if sample.get("is_effective") else f"空闲 ({sample.get('idle_seconds', 0):.0f}s)"
        self.lbl_status.setText(f"状态: {status}")

        # Refresh table
        self.table.setRowCount(len(self._samples))
        for i, s in enumerate(self._samples):
            self.table.setItem(i, 0, QTableWidgetItem(s["timestamp"][-8:]))
            self.table.setItem(i, 1, QTableWidgetItem(s.get("process_name", "")))
            self.table.setItem(i, 2, QTableWidgetItem(s.get("category_name", "")))
            self.table.setItem(i, 3, QTableWidgetItem("✓" if s.get("is_effective") else "✗"))
