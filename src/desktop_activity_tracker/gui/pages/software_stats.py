"""Software stats page - per-app usage table with export."""

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QFileDialog, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush

from ... import database
from ...utils import fmt_seconds
from ..style import COLORS, BUTTON_PRIMARY_STYLE, BUTTON_SECONDARY_STYLE, SECTION_TITLE, get_category_color


class SoftwareStatsPage(QWidget):
    def __init__(self, db_path, reports_dir):
        super().__init__()
        self.db_path = db_path
        self.reports_dir = reports_dir

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("软件统计")
        title.setStyleSheet(SECTION_TITLE)
        layout.addWidget(title)

        # Buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_export_csv = QPushButton("导出 CSV")
        btn_export_csv.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_export_csv.setCursor(Qt.PointingHandCursor)
        btn_export_csv.clicked.connect(self._export_csv)

        btn_export_md = QPushButton("导出 Markdown")
        btn_export_md.setStyleSheet(BUTTON_PRIMARY_STYLE)
        btn_export_md.setCursor(Qt.PointingHandCursor)
        btn_export_md.clicked.connect(self._export_md)

        btn_layout.addWidget(btn_export_csv)
        btn_layout.addWidget(btn_export_md)
        btn_layout.addStretch()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['coding_green']}; font-weight: 600;"
        )
        btn_layout.addWidget(self.status_label)
        layout.addLayout(btn_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["软件", "窗口标题", "分类", "有效时长", "占比"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: {COLORS['panel_bg']};
                alternate-background-color: {COLORS['panel_bg_alt']};
                color: {COLORS['text']};
                gridline-color: {COLORS['border']};
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
            }}
            QTableWidget::item {{
                padding: 8px;
                border: none;
            }}
            QTableWidget::item:selected {{
                background: {COLORS['primary']};
                color: {COLORS['text_inverse']};
            }}
            QHeaderView::section {{
                background: {COLORS['card_bg_alt']};
                color: {COLORS['text_secondary']};
                border: none;
                padding: 10px 8px;
                font-weight: 700;
                font-size: 13px;
            }}
        """)
        layout.addWidget(self.table, 1)

        self.refresh()

    def refresh(self):
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            details = stats.get("by_app_detail", [])
            total_eff = stats.get("totals", {}).get("effective_seconds", 0) or 1
            self.table.setRowCount(len(details))
            for i, app in enumerate(details):
                pname = app.get("process_name", "")
                self.table.setItem(i, 0, QTableWidgetItem(pname))
                title = app.get("window_title", "") or "-"
                self.table.setItem(i, 1, QTableWidgetItem(title[:60]))
                cat_name = ""
                cat_key = ""
                for a in stats.get("by_app", []):
                    if a["process_name"] == pname:
                        cat_name = a.get("category_name", "")
                        cat_key = a.get("category_key", "")
                        break
                cat_item = QTableWidgetItem(f"● {cat_name}")
                cat_color = get_category_color(cat_key)
                cat_item.setForeground(QBrush(QColor(cat_color)))
                self.table.setItem(i, 2, cat_item)
                secs = app.get("effective_seconds", 0) or 0
                self.table.setItem(i, 3, QTableWidgetItem(fmt_seconds(secs)))
                pct = f"{round(secs / total_eff * 100)}%" if total_eff > 0 else "0%"
                self.table.setItem(i, 4, QTableWidgetItem(pct))
        except Exception as e:
            import sys, traceback
            print(f"[SoftwareStats] refresh error: {e}", file=sys.stderr)
            traceback.print_exc()

    def _export_csv(self):
        from ... import exporter
        today = datetime.now().strftime("%Y-%m-%d")
        default_name = f"usage_{today}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", default_name, "CSV 文件 (*.csv);;所有文件 (*)"
        )
        if not path:
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['text_muted']}; font-weight: 600;"
            )
            self.status_label.setText("已取消导出")
            return
        try:
            exporter.export_csv(self.db_path, today, os.path.dirname(path))
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['coding_green']}; font-weight: 600;"
            )
            self.status_label.setText(f"CSV 已保存 → {os.path.basename(path)}")
        except Exception as e:
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['danger_red']}; font-weight: 600;"
            )
            self.status_label.setText(f"导出失败: {e}")

    def _export_md(self):
        from ... import exporter
        today = datetime.now().strftime("%Y-%m-%d")
        default_name = f"{today}.md"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Markdown 日报", default_name,
            "Markdown 文件 (*.md);;所有文件 (*)"
        )
        if not path:
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['text_muted']}; font-weight: 600;"
            )
            self.status_label.setText("已取消导出")
            return
        try:
            exporter.export_markdown(self.db_path, today, os.path.dirname(path))
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['coding_green']}; font-weight: 600;"
            )
            self.status_label.setText(f"日报已保存 → {os.path.basename(path)}")
        except Exception as e:
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['danger_red']}; font-weight: 600;"
            )
            self.status_label.setText(f"导出失败: {e}")
