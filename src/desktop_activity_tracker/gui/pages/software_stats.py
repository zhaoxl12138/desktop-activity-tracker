"""Software stats page - per-app usage table with export buttons."""

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QMessageBox
)

from ... import database
from ...utils import fmt_seconds
from ..style import TABLE_STYLE, BUTTON_PRIMARY_STYLE, BUTTON_SECONDARY_STYLE


class SoftwareStatsPage(QWidget):
    def __init__(self, db_path, reports_dir):
        super().__init__()
        self.db_path = db_path
        self.reports_dir = reports_dir

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("软件统计")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_export_csv = QPushButton("导出 CSV")
        btn_export_csv.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_export_csv.clicked.connect(self._export_csv)
        btn_export_md = QPushButton("导出 Markdown")
        btn_export_md.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_export_md.clicked.connect(self._export_md)
        btn_layout.addWidget(btn_export_csv)
        btn_layout.addWidget(btn_export_md)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["软件", "关键词", "分类", "有效时长", "占比"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet(TABLE_STYLE)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self):
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            details = stats.get("by_app_detail", [])
            total_eff = stats.get("totals", {}).get("effective_seconds", 0) or 1
            self.table.setRowCount(len(details))
            for i, app in enumerate(details):
                self.table.setItem(i, 0, QTableWidgetItem(app.get("process_name", "")))
                title = app.get("window_title", "") or "-"
                keyword = title[:40]
                self.table.setItem(i, 1, QTableWidgetItem(keyword))
                # Look up category for this process
                cat_name = ""
                for a in stats.get("by_app", []):
                    if a["process_name"] == app["process_name"]:
                        cat_name = a.get("category_name", "")
                        break
                self.table.setItem(i, 2, QTableWidgetItem(cat_name))
                secs = app.get("effective_seconds", 0) or 0
                self.table.setItem(i, 3, QTableWidgetItem(fmt_seconds(secs)))
                pct = f"{round(secs / total_eff * 100)}%" if total_eff > 0 else "0%"
                self.table.setItem(i, 4, QTableWidgetItem(pct))
        except Exception:
            pass

    def _export_csv(self):
        from ... import exporter
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.reports_dir, "daily")
        try:
            path = exporter.export_csv(self.db_path, today, daily_dir)
            QMessageBox.information(self, "导出成功", f"CSV 已保存到\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _export_md(self):
        from ... import exporter
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.reports_dir, "daily")
        try:
            path = exporter.export_markdown(self.db_path, today, daily_dir)
            QMessageBox.information(self, "导出成功", f"日报已保存到\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
