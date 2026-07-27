"""Software stats page - per-app usage table with export."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services import software_stats_service
from .. import style as ui_style
from ..style import COLORS, get_category_color


class SoftwareStatsPage(QWidget):
    def __init__(self, db_path, reports_dir, display_name_mapping=None):
        super().__init__()
        self.db_path = db_path
        self.reports_dir = reports_dir
        self.display_name_mapping = display_name_mapping or {}
        self._is_active = False
        self._last_rows_signature = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("软件统计")
        title.setStyleSheet(ui_style.get_section_title())
        layout.addWidget(title)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        btn_export_csv = QPushButton("导出 CSV")
        btn_export_csv.setStyleSheet(ui_style.get_button_secondary_style())
        btn_export_csv.setCursor(Qt.PointingHandCursor)
        btn_export_csv.clicked.connect(self._export_csv)

        btn_export_md = QPushButton("导出 Markdown")
        btn_export_md.setStyleSheet(ui_style.get_button_primary_style())
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

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["软件", "窗口标题", "分类", "有效时长", "占比"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            f"""
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
            """
        )
        layout.addWidget(self.table, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.setInterval(30000)

    def activate(self, force: bool = False) -> None:
        self._is_active = True
        if not self.timer.isActive():
            self.timer.start()
        if force or self._last_rows_signature is None:
            self.refresh()

    def deactivate(self) -> None:
        self._is_active = False
        self.timer.stop()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.activate()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.deactivate()
        super().hideEvent(event)

    def refresh(self):
        if not self._is_active:
            return
        try:
            rows = software_stats_service.load_software_rows(self.db_path, self.display_name_mapping)
            signature = tuple(
                (row.get("software"), row.get("title"), row.get("category_key"),
                 row.get("duration"), row.get("percent"))
                for row in rows
            )
            if signature == self._last_rows_signature:
                return
            self._last_rows_signature = signature
            self.table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                software_item = QTableWidgetItem(str(row["software"]))
                software_item.setToolTip(str(row["software"]))
                self.table.setItem(index, 0, software_item)
                title_item = QTableWidgetItem(str(row["title"]))
                title_item.setToolTip(str(row["title"]))
                self.table.setItem(index, 1, title_item)
                cat_item = QTableWidgetItem(f"● {row['category_name']}")
                cat_item.setToolTip(str(row["category_name"]))
                cat_item.setForeground(QBrush(QColor(get_category_color(str(row["category_key"])))))
                self.table.setItem(index, 2, cat_item)
                self.table.setItem(index, 3, QTableWidgetItem(str(row["duration"])))
                self.table.setItem(index, 4, QTableWidgetItem(str(row["percent"])))
        except Exception as exc:
            import sys
            import traceback

            print(f"[SoftwareStats] refresh error: {exc}", file=sys.stderr)
            traceback.print_exc()

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "usage_today.csv", "CSV 文件 (*.csv);;所有文件 (*)"
        )
        if not path:
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['text_muted']}; font-weight: 600;"
            )
            self.status_label.setText("已取消导出")
            return
        try:
            saved_path = software_stats_service.export_software_csv(self.db_path, path)
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['coding_green']}; font-weight: 600;"
            )
            self.status_label.setText(f"CSV 已保存 → {saved_path}")
        except Exception as exc:
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['danger_red']}; font-weight: 600;"
            )
            self.status_label.setText(f"导出失败: {exc}")

    def _export_md(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Markdown 日报", "today.md", "Markdown 文件 (*.md);;所有文件 (*)"
        )
        if not path:
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['text_muted']}; font-weight: 600;"
            )
            self.status_label.setText("已取消导出")
            return
        try:
            saved_path = software_stats_service.export_software_markdown(self.db_path, path)
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['coding_green']}; font-weight: 600;"
            )
            self.status_label.setText(f"日报已保存 → {saved_path}")
        except Exception as exc:
            self.status_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS['danger_red']}; font-weight: 600;"
            )
            self.status_label.setText(f"导出失败: {exc}")

