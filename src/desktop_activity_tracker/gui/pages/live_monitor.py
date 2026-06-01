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
        self._samples = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # Compact info panel — 2 rows × 4 columns in a styled card
        info = QFrame()
        info.setStyleSheet(
            f"background: {COLORS['card_bg']}; border: 1px solid {COLORS['border']};"
            f"border-radius: 10px; padding: 14px 18px;"
        )
        grid = QGridLayout(info)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setVerticalSpacing(6)
        grid.setHorizontalSpacing(20)

        self.lbl_process = QLabel("--")
        self.lbl_title = QLabel("--")
        self.lbl_category = QLabel("--")
        self.lbl_duration = QLabel("--")
        self.lbl_effective = QLabel("--")
        self.lbl_session_idle = QLabel("--")
        self.lbl_idle = QLabel("--")
        self.lbl_status = QLabel("--")

        items = [
            ("进程", self.lbl_process), ("窗口", self.lbl_title),
            ("分类", self.lbl_category), ("前台停留", self.lbl_duration),
            ("有效时间", self.lbl_effective), ("挂机时间", self.lbl_session_idle),
            ("空闲秒数", self.lbl_idle), ("状态", self.lbl_status),
        ]
        for i, (label_text, widget) in enumerate(items):
            row, col = i % 4, (i // 4) * 2
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']}; font-weight: 600;")
            widget.setStyleSheet(f"font-size: 12px; color: {COLORS['text']}; font-weight: 600;")
            grid.addWidget(lbl, row, col)
            grid.addWidget(widget, row, col + 1)

        layout.addWidget(info)

        # History table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["时间", "进程", "归一化标题", "分类", "有效"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
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
        idle_s = sample.get('idle_seconds', 0) or 0

        self.lbl_process.setText(proc)
        self.lbl_title.setText(title)
        self.lbl_category.setText(cat_name)
        self.lbl_category.setStyleSheet(
            f"font-size: 12px; color: {get_category_color(cat_key)}; font-weight: 700;"
        )
        self.lbl_duration.setText(fmt_seconds(dur))
        self.lbl_effective.setText(fmt_seconds(eff))
        self.lbl_session_idle.setText(fmt_seconds(sidle))
        self.lbl_idle.setText(f"{idle_s:.0f}s")

        if sample.get("is_effective"):
            self.lbl_status.setText("● 有效")
            self.lbl_status.setStyleSheet(
                f"font-size: 12px; color: {COLORS['success_green']}; font-weight: 700;"
            )
        else:
            self.lbl_status.setText(f"◉ 挂机 {idle_s:.0f}s")
            self.lbl_status.setStyleSheet(
                f"font-size: 12px; color: {COLORS['warning_yellow']}; font-weight: 700;"
            )

        self.table.setRowCount(len(self._samples))
        for i, s in enumerate(self._samples):
            self.table.setItem(i, 0, QTableWidgetItem(s["timestamp"][-8:]))
            self.table.setItem(i, 1, QTableWidgetItem(s.get("process_name", "")))
            self.table.setItem(i, 2, QTableWidgetItem(s.get("normalized_title", "") or s.get("window_title", "")))
            self.table.setItem(i, 3, QTableWidgetItem(s.get("category_name", "")))
            self.table.setItem(i, 4, QTableWidgetItem("✓" if s.get("is_effective") else "✗"))
