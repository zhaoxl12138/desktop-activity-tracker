"""Live monitor page — compact current session + sample history table."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QGridLayout
)

from ...utils import fmt_seconds
from ..style import COLORS, TABLE_STYLE, get_category_color


class LiveMonitorPage(QWidget):
    def __init__(self):
        super().__init__()
        self._samples = []  # last 20 samples

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Title row
        title = QLabel("实时监控")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        # Compact 4-column info grid
        info = QFrame()
        info.setStyleSheet(
            "background: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 6px; padding: 10px;"
        )
        grid = QGridLayout(info)
        grid.setContentsMargins(8, 6, 8, 6)
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(16)

        cell_style = "font-size: 12px; color: #2C3E50;"

        self.lbl_process = QLabel("--")
        self.lbl_title = QLabel("--")
        self.lbl_category = QLabel("--")
        self.lbl_duration = QLabel("--")
        self.lbl_effective = QLabel("--")
        self.lbl_session_idle = QLabel("--")
        self.lbl_idle = QLabel("--")
        self.lbl_status = QLabel("--")

        widgets = [
            ("进程", self.lbl_process), ("窗口", self.lbl_title),
            ("分类", self.lbl_category), ("前台停留", self.lbl_duration),
            ("有效时间", self.lbl_effective), ("挂机时间", self.lbl_session_idle),
            ("空闲秒数", self.lbl_idle), ("状态", self.lbl_status),
        ]
        for i, (label, widget) in enumerate(widgets):
            row, col = i % 4, (i // 4) * 2
            lbl_key = QLabel(label)
            lbl_key.setStyleSheet("font-size: 11px; color: #7F8C8D;")
            widget.setStyleSheet(cell_style)
            grid.addWidget(lbl_key, row, col)
            grid.addWidget(widget, row, col + 1)

        layout.addWidget(info)

        # History table fills remaining space
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["时间", "进程", "归一化标题", "分类", "有效"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setDefaultSectionSize(80)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setMinimumHeight(200)
        layout.addWidget(self.table, 1)

    def on_sample_updated(self, sample):
        self._samples.insert(0, sample)
        if len(self._samples) > 20:
            self._samples = self._samples[:20]

        proc = sample.get('process_name', '--')
        title = sample.get('window_title', '--')[:60]
        cat_name = sample.get('category_name', '--')
        cat_key = sample.get('category_key', 'other')
        dur = sample.get('duration_seconds', 0) or 0
        eff = sample.get('effective_seconds', 0) or 0
        sidle = sample.get('session_idle_seconds', 0) or 0

        self.lbl_process.setText(proc)
        self.lbl_title.setText(title)
        self.lbl_category.setText(cat_name)
        self.lbl_category.setStyleSheet(f"font-size: 12px; color: {get_category_color(cat_key)}; font-weight: bold;")
        self.lbl_duration.setText(fmt_seconds(dur))
        self.lbl_effective.setText(fmt_seconds(eff))
        self.lbl_session_idle.setText(fmt_seconds(sidle))
        self.lbl_idle.setText(f"{sample.get('idle_seconds', 0):.0f}s")

        if sample.get("is_effective"):
            self.lbl_status.setText("有效计时")
            self.lbl_status.setStyleSheet("font-size: 12px; color: #2ECC71; font-weight: bold;")
        else:
            idle_s = sample.get('idle_seconds', 0) or 0
            self.lbl_status.setText(f"挂机 {idle_s:.0f}s")
            self.lbl_status.setStyleSheet("font-size: 12px; color: #E67E22; font-weight: bold;")

        self.table.setRowCount(len(self._samples))
        for i, s in enumerate(self._samples):
            self.table.setItem(i, 0, QTableWidgetItem(s["timestamp"][-8:]))
            self.table.setItem(i, 1, QTableWidgetItem(s.get("process_name", "")))
            self.table.setItem(i, 2, QTableWidgetItem(s.get("normalized_title", "") or s.get("window_title", "")))
            self.table.setItem(i, 3, QTableWidgetItem(s.get("category_name", "")))
            self.table.setItem(i, 4, QTableWidgetItem("✓" if s.get("is_effective") else "✗"))
