"""Main application window with sidebar navigation and stacked pages."""

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from .. import database
from ..exporter import _fmt_seconds

from .style import (
    COLORS, SIDEBAR_STYLE, TOP_BAR_STYLE, BOTTOM_BAR_STYLE,
    BUTTON_PRIMARY_STYLE, BUTTON_SECONDARY_STYLE
)
from .pages.today_overview import TodayOverviewPage
from .pages.live_monitor import LiveMonitorPage
from .pages.software_stats import SoftwareStatsPage
from .pages.category_stats import CategoryStatsPage
from .pages.reports import ReportsPage
from .pages.rule_config import RuleConfigPage
from .pages.settings import SettingsPage


NAV_ITEMS = [
    ("今日概览", "today"),
    ("实时监控", "live"),
    ("软件统计", "software"),
    ("分类统计", "category"),
    ("日报/周报", "reports"),
    ("规则配置", "rules"),
    ("设置", "settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, app_root, config, db_path, config_path, reports_dir, worker):
        super().__init__()
        self.app_root = app_root
        self.config = config
        self.db_path = db_path
        self.config_path = config_path
        self.reports_dir = reports_dir
        self.worker = worker

        self.setWindowTitle("Desktop Activity Tracker")
        self.resize(900, 620)
        self.setMinimumSize(800, 540)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top bar ──
        root_layout.addWidget(self._build_top_bar())

        # ── Main content: sidebar + pages ──
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)

        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(160)
        self.nav_list.setStyleSheet(SIDEBAR_STYLE)
        self.nav_list.setFont(QFont("Microsoft YaHei", 10))
        for name, key in NAV_ITEMS:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, key)
            self.nav_list.addItem(item)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)

        self.stack = QStackedWidget()

        self.pages = {}
        self.pages['today'] = TodayOverviewPage(self.db_path)
        self.pages['live'] = LiveMonitorPage()
        self.pages['software'] = SoftwareStatsPage(self.db_path, self.reports_dir)
        self.pages['category'] = CategoryStatsPage(self.db_path)
        obsidian_path = self.config.get("obsidian_output_path", "").strip()
        self.pages['reports'] = ReportsPage(self.db_path, self.reports_dir, obsidian_path)
        self.pages['rules'] = RuleConfigPage(self.config_path)
        self.pages['settings'] = SettingsPage(self.config_path, self.db_path, self.reports_dir)

        for _, key in NAV_ITEMS:
            self.stack.addWidget(self.pages[key])

        content.addWidget(self.nav_list)
        content.addWidget(self.stack, 1)
        root_layout.addLayout(content)

        # ── Bottom status bar ──
        root_layout.addWidget(self._build_bottom_bar())

        # Connect worker signal
        self.worker.sample_updated.connect(self._on_sample)

        # Select first page
        self.nav_list.setCurrentRow(0)

        # Summary refresh timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_top_bar)
        self.refresh_timer.start(30000)

    def _build_top_bar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setStyleSheet(TOP_BAR_STYLE)
        bar.setFixedHeight(60)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)

        title = QLabel("Desktop Activity Tracker")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        self.top_summary = QLabel()
        self.top_summary.setStyleSheet("font-size: 13px; color: #7F8C8D;")
        self._update_top_bar()
        layout.addWidget(self.top_summary)

        layout.addStretch()

        self.btn_pause = QPushButton("暂停")
        self.btn_pause.setStyleSheet(BUTTON_SECONDARY_STYLE)
        self.btn_pause.clicked.connect(self._toggle_pause)
        layout.addWidget(self.btn_pause)

        btn_report = QPushButton("生成日报")
        btn_report.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_report.clicked.connect(self._quick_report)
        layout.addWidget(btn_report)

        return bar

    def _build_bottom_bar(self):
        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar.setStyleSheet(BOTTOM_BAR_STYLE)
        bar.setFixedHeight(28)

        self.lbl_status = QLabel("状态: 记录中")
        self.lbl_status.setStyleSheet("color: #2ECC71; font-weight: bold;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 2, 16, 2)
        layout.addWidget(self.lbl_status)
        layout.addStretch()
        self.lbl_time = QLabel()
        layout.addWidget(self.lbl_time)
        return bar

    def _on_nav_changed(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _on_sample(self, sample):
        if self.stack.currentWidget() is self.pages.get('live'):
            self.pages['live'].on_sample_updated(sample)
        now = datetime.now().strftime("%H:%M:%S")
        self.lbl_time.setText(f"最后采样: {now}")

    def _toggle_pause(self):
        if self.worker.is_paused():
            self.worker.resume()
            self.btn_pause.setText("暂停")
            self.lbl_status.setText("状态: 记录中")
            self.lbl_status.setStyleSheet("color: #2ECC71; font-weight: bold;")
        else:
            self.worker.pause()
            self.btn_pause.setText("恢复")
            self.lbl_status.setText("状态: 已暂停")
            self.lbl_status.setStyleSheet("color: #E67E22; font-weight: bold;")

    def _update_top_bar(self):
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            effective = stats['totals'].get('effective_seconds', 0) or 0
            work_cats = {"ai_tools", "coding", "reading"}
            work_sec = sum(c['effective_seconds'] for c in stats['by_category'] if c['category_key'] in work_cats)
            video_sec = sum(c['effective_seconds'] for c in stats['by_category'] if c['category_key'] == 'video')
            self.top_summary.setText(
                f"今日有效: {_fmt_seconds(effective)}  |  "
                f"学习/工作: {_fmt_seconds(work_sec)}  |  "
                f"娱乐: {_fmt_seconds(video_sec)}"
            )
        except Exception:
            pass

    def _quick_report(self):
        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.reports_dir, "daily")
        os.makedirs(daily_dir, exist_ok=True)
        from .. import exporter
        try:
            path = exporter.export_markdown(self.db_path, today, daily_dir)
            obsidian_path = self.config.get("obsidian_output_path", "").strip()
            if obsidian_path:
                exporter.sync_to_obsidian(path, obsidian_path)
            QMessageBox.information(self, "生成成功", f"日报已保存到\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "生成失败", str(e))

    def closeEvent(self, event):
        """Minimize to tray instead of quitting."""
        event.ignore()
        self.hide()
        if hasattr(self, 'tray'):
            self.tray.showMessage("Desktop Activity Tracker", "程序已最小化到系统托盘\n右键托盘图标可退出")
