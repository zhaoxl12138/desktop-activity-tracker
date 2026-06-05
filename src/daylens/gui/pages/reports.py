"""Reports page - list generated reports, generate new ones, sync to Obsidian."""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QMessageBox, QTabWidget, QFrame
)
from PySide6.QtCore import Qt, QTimer

from ...services import reports_service
from .. import style as ui_style


class ReportsPage(QWidget):
    def __init__(self, db_path, reports_dir, obsidian_path=""):
        super().__init__()
        self.db_path = db_path
        self.reports_dir = reports_dir
        self.obsidian_path = obsidian_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        lbl = QLabel("报告管理")
        lbl.setStyleSheet(ui_style.get_section_title())
        layout.addWidget(lbl)

        # Generation buttons row
        gen_frame = QFrame()
        gen_frame.setObjectName("dashboardCard")
        gen_frame.setStyleSheet(ui_style.get_dashboard_card_style())
        gen_layout = QHBoxLayout(gen_frame)
        gen_layout.setContentsMargins(12, 8, 12, 8)
        gen_layout.setSpacing(10)

        gen_label = QLabel("生成报告:")
        gen_label.setStyleSheet(f"font-size: 13px; color: {ui_style.COLORS['text_secondary']}; font-weight: 600;")
        gen_layout.addWidget(gen_label)

        btn_daily = QPushButton("今日日报")
        btn_daily.setStyleSheet(ui_style.get_button_primary_style())
        btn_daily.setCursor(Qt.PointingHandCursor)
        btn_daily.clicked.connect(self._generate_daily)

        btn_weekly = QPushButton("本周周报")
        btn_weekly.setStyleSheet(ui_style.get_button_primary_style())
        btn_weekly.setCursor(Qt.PointingHandCursor)
        btn_weekly.clicked.connect(self._generate_weekly)

        btn_monthly = QPushButton("本月月报")
        btn_monthly.setStyleSheet(ui_style.get_button_primary_style())
        btn_monthly.setCursor(Qt.PointingHandCursor)
        btn_monthly.clicked.connect(self._generate_monthly)

        gen_layout.addWidget(btn_daily)
        gen_layout.addWidget(btn_weekly)
        gen_layout.addWidget(btn_monthly)
        gen_layout.addStretch()

        btn_open_dir = QPushButton("打开报告目录")
        btn_open_dir.setStyleSheet(ui_style.get_button_secondary_style())
        btn_open_dir.setCursor(Qt.PointingHandCursor)
        btn_open_dir.clicked.connect(lambda: os.startfile(self.reports_dir) if os.path.exists(self.reports_dir) else None)

        btn_obsidian = QPushButton("同步到 Obsidian")
        btn_obsidian.setStyleSheet(ui_style.get_button_secondary_style())
        btn_obsidian.setCursor(Qt.PointingHandCursor)
        btn_obsidian.clicked.connect(self._sync_obsidian)

        gen_layout.addWidget(btn_open_dir)
        gen_layout.addWidget(btn_obsidian)
        layout.addWidget(gen_frame)

        # Tabs: daily / weekly / monthly
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {ui_style.COLORS['border']};
                border-radius: 12px;
                background: {ui_style.COLORS['card_bg']};
            }}
            QTabBar::tab {{
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 600;
                color: {ui_style.COLORS['text_secondary']};
                background: {ui_style.COLORS['panel_bg']};
                border: 1px solid {ui_style.COLORS['border']};
                border-radius: 10px;
                border-bottom: 2px solid transparent;
                margin-right: 6px;
            }}
            QTabBar::tab:selected {{
                color: {ui_style.COLORS['text_inverse']};
                background: {ui_style.COLORS['primary']};
                border-bottom: 2px solid {ui_style.COLORS['primary']};
            }}
            QTabBar::tab:hover:!selected {{
                color: {ui_style.COLORS['text']};
            }}
        """)
        self.tab_daily = self._make_table()
        self.tab_weekly = self._make_table()
        self.tab_monthly = self._make_table()

        self.tabs.addTab(self.tab_daily, "日报")
        self.tabs.addTab(self.tab_weekly, "周报")
        self.tabs.addTab(self.tab_monthly, "月报")
        layout.addWidget(self.tabs, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(60000)
        self.refresh()

    def _make_table(self):
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["日期/标识", "文件名", "大小"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setStyleSheet(ui_style.get_table_style())
        return table

    def refresh(self):
        for tab, subdir in [
            (self.tab_daily, "daily"),
            (self.tab_weekly, "weekly"),
            (self.tab_monthly, "monthly"),
        ]:
            rows = reports_service.list_report_rows(self.reports_dir, subdir, limit=50)
            tab.setRowCount(len(rows))
            for i, (label, filename, size_text) in enumerate(rows):
                tab.setItem(i, 0, QTableWidgetItem(label))
                tab.setItem(i, 1, QTableWidgetItem(filename))
                tab.setItem(i, 2, QTableWidgetItem(size_text))

    # ── Generation actions ──

    def _generate_daily(self):
        try:
            path = reports_service.generate_daily_report(self.db_path, self.reports_dir)
            self._sync_one(path)
            QMessageBox.information(self, "生成成功", f"日报已保存\n{path}")
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "生成失败", str(e))

    def _generate_weekly(self):
        try:
            path = reports_service.generate_weekly_report(self.db_path, self.reports_dir)
            self._sync_one(path)
            QMessageBox.information(self, "生成成功", f"周报已保存\n{path}")
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "生成失败", str(e))

    def _generate_monthly(self):
        try:
            path = reports_service.generate_monthly_report(self.db_path, self.reports_dir)
            self._sync_one(path)
            QMessageBox.information(self, "生成成功", f"月报已保存\n{path}")
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "生成失败", str(e))

    # ── Obsidian sync ──

    def _sync_obsidian(self):
        if not self.obsidian_path:
            QMessageBox.warning(self, "未配置", "请在设置页配置 Obsidian 输出路径。")
            return
        md_file = reports_service.today_report_path(self.reports_dir)
        if not os.path.exists(md_file):
            QMessageBox.warning(self, "无日报", "请先生成今日日报。")
            return
        self._sync_one(md_file)

    def _sync_one(self, filepath):
        if self.obsidian_path and os.path.exists(filepath):
            reports_service.sync_report_to_obsidian(filepath, self.obsidian_path)
