"""Reports page - list generated reports, generate new ones, sync to Obsidian."""

import os
import glob
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QMessageBox, QTabWidget
)
from PySide6.QtCore import QTimer

from ... import exporter
from ..style import TABLE_STYLE, BUTTON_PRIMARY_STYLE, BUTTON_SECONDARY_STYLE


class ReportsPage(QWidget):
    def __init__(self, db_path, reports_dir, obsidian_path=""):
        super().__init__()
        self.db_path = db_path
        self.reports_dir = reports_dir
        self.obsidian_path = obsidian_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        lbl = QLabel("报告管理")
        lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(lbl)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_gen = QPushButton("生成今日日报")
        btn_gen.setStyleSheet(BUTTON_PRIMARY_STYLE)
        btn_gen.clicked.connect(self._generate_today)
        btn_open_dir = QPushButton("打开报告目录")
        btn_open_dir.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_open_dir.clicked.connect(lambda: os.startfile(self.reports_dir) if os.path.exists(self.reports_dir) else None)
        btn_obsidian = QPushButton("复制到 Obsidian")
        btn_obsidian.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_obsidian.clicked.connect(self._sync_obsidian)
        btn_layout.addWidget(btn_gen)
        btn_layout.addWidget(btn_open_dir)
        btn_layout.addWidget(btn_obsidian)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Tabs: daily / weekly / monthly
        self.tabs = QTabWidget()
        self.tab_daily = QTableWidget()
        self.tab_weekly = QTableWidget()
        self.tab_monthly = QTableWidget()
        for tab, name in [(self.tab_daily, "日报"), (self.tab_weekly, "周报"), (self.tab_monthly, "月报")]:
            tab.setColumnCount(3)
            tab.setHorizontalHeaderLabels(["日期", "文件", "大小"])
            tab.horizontalHeader().setStretchLastSection(True)
            tab.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tab.setEditTriggers(QTableWidget.NoEditTriggers)
            tab.setStyleSheet(TABLE_STYLE)
            self.tabs.addTab(tab, name)
        layout.addWidget(self.tabs)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(60000)
        self.refresh()

    def refresh(self):
        for tab, subdir in [(self.tab_daily, "daily"), (self.tab_weekly, "weekly"), (self.tab_monthly, "monthly")]:
            d = os.path.join(self.reports_dir, subdir)
            files = sorted(glob.glob(os.path.join(d, "*.md")), reverse=True)[:50]
            tab.setRowCount(len(files))
            for i, f in enumerate(files):
                fname = os.path.basename(f)
                tab.setItem(i, 0, QTableWidgetItem(fname.replace('.md', '')))
                tab.setItem(i, 1, QTableWidgetItem(fname))
                size_kb = os.path.getsize(f) // 1024 if os.path.exists(f) else 0
                tab.setItem(i, 2, QTableWidgetItem(f"{size_kb} KB"))

    def _generate_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.reports_dir, "daily")
        try:
            path = exporter.export_markdown(self.db_path, today, daily_dir)
            self._sync_one(path)
            QMessageBox.information(self, "生成成功", f"日报已保存\n{path}")
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "生成失败", str(e))

    def _sync_obsidian(self):
        if not self.obsidian_path:
            QMessageBox.warning(self, "未配置", "请在设置页配置 Obsidian 输出路径。")
            return
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.reports_dir, "daily")
        md_file = os.path.join(daily_dir, f"{today}.md")
        if not os.path.exists(md_file):
            QMessageBox.warning(self, "无日报", "请先生成今日日报。")
            return
        self._sync_one(md_file)

    def _sync_one(self, filepath):
        if self.obsidian_path and os.path.exists(filepath):
            exporter.sync_to_obsidian(filepath, self.obsidian_path)
