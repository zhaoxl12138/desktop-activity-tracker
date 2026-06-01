"""Main application window with sidebar navigation and stacked pages."""

import os
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import database
from ..utils import fmt_seconds
from .pages.category_stats import CategoryStatsPage
from .pages.live_monitor import LiveMonitorPage
from .pages.reports import ReportsPage
from .pages.rule_config import RuleConfigPage
from .pages.settings import SettingsPage
from .pages.software_stats import SoftwareStatsPage
from .pages.today_overview import TodayOverviewPage
from .style import (
    BOTTOM_BAR_STYLE,
    BUTTON_DANGER_STYLE,
    BUTTON_PRIMARY_STYLE,
    BUTTON_SECONDARY_STYLE,
    COLORS,
    GLOBAL_STYLE,
    INPUT_STYLE,
    SIDEBAR_STYLE,
    TOP_BAR_STYLE,
)


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
        self.setStyleSheet(GLOBAL_STYLE + INPUT_STYLE)
        self.resize(1220, 820)
        self.setMinimumSize(1080, 700)

        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_top_bar())

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self._build_sidebar())
        content.addWidget(self._build_pages(), 1)
        root_layout.addLayout(content, 1)

        root_layout.addWidget(self._build_bottom_bar())

        self.worker.sample_updated.connect(self._on_sample)
        self.nav_list.setCurrentRow(0)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_top_bar)
        self.refresh_timer.start(30000)

    def _build_sidebar(self):
        frame = QFrame()
        frame.setFixedWidth(236)
        frame.setStyleSheet(f"background: {COLORS['sidebar_bg']};")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 18, 0, 16)
        layout.setSpacing(0)

        brand = QLabel("Desktop\nActivity Tracker")
        brand.setStyleSheet(
            f"""
            font-size: 19px;
            font-weight: 800;
            color: {COLORS['text_inverse']};
            letter-spacing: 0.5px;
            padding: 12px 20px 18px 20px;
            """
        )
        layout.addWidget(brand)

        tagline = QLabel("把时间结构看清楚")
        tagline.setStyleSheet(
            f"font-size: 11px; color: {COLORS['text_muted']}; padding: 0 20px 18px 20px;"
        )
        layout.addWidget(tagline)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {COLORS['sidebar_hover']}; margin: 0 14px;")
        layout.addWidget(divider)

        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet(SIDEBAR_STYLE)
        self.nav_list.setFont(QFont("Microsoft YaHei", 9))
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_list.setWordWrap(True)
        for name, key in NAV_ITEMS:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, key)
            self.nav_list.addItem(item)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav_list)

        layout.addStretch()

        version = QLabel("v1.2.0")
        version.setStyleSheet(
            f"font-size: 10px; color: {COLORS['text_muted']}; padding: 10px 16px;"
        )
        layout.addWidget(version)
        return frame

    def _build_pages(self):
        self.stack = QStackedWidget()
        self.pages = {
            "today": TodayOverviewPage(self.db_path),
            "live": LiveMonitorPage(),
            "software": SoftwareStatsPage(self.db_path, self.reports_dir),
            "category": CategoryStatsPage(self.db_path),
        }

        obsidian_path = self.config.get("obsidian_output_path", "").strip()
        self.pages["reports"] = ReportsPage(self.db_path, self.reports_dir, obsidian_path)
        self.pages["rules"] = RuleConfigPage(self.config_path)
        self.pages["settings"] = SettingsPage(
            self.config_path, self.db_path, self.reports_dir, self.worker
        )

        for _, key in NAV_ITEMS:
            self.stack.addWidget(self.pages[key])
        return self.stack

    def _build_top_bar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setStyleSheet(TOP_BAR_STYLE)
        bar.setFixedHeight(72)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 20, 0)

        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(2)

        self.lbl_page_title = QLabel("今日概览")
        self.lbl_page_title.setStyleSheet(
            f"font-size: 24px; font-weight: 800; color: {COLORS['text']};"
        )
        title_wrap.addWidget(self.lbl_page_title)

        self.lbl_page_hint = QLabel("聚焦今天的使用结构、效率与提醒")
        self.lbl_page_hint.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_secondary']};"
        )
        title_wrap.addWidget(self.lbl_page_hint)

        layout.addLayout(title_wrap)
        layout.addSpacing(20)

        self.top_summary = QLabel()
        self.top_summary.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']}; font-weight: 600;"
        )
        self._update_top_bar()
        layout.addWidget(self.top_summary)
        layout.addStretch()

        self.btn_pause = QPushButton("⏸ 暂停")
        self.btn_pause.setStyleSheet(BUTTON_SECONDARY_STYLE)
        self.btn_pause.setCursor(Qt.PointingHandCursor)
        self.btn_pause.clicked.connect(self._toggle_pause)
        layout.addWidget(self.btn_pause)

        btn_report = QPushButton("生成日报")
        btn_report.setStyleSheet(BUTTON_PRIMARY_STYLE)
        btn_report.setCursor(Qt.PointingHandCursor)
        btn_report.clicked.connect(self._quick_report)
        layout.addWidget(btn_report)
        return bar

    def _build_bottom_bar(self):
        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar.setStyleSheet(BOTTOM_BAR_STYLE)
        bar.setFixedHeight(36)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {COLORS['success_green']}; border-radius: 4px;")
        self._status_dot = dot
        layout.addWidget(dot)

        self.lbl_status = QLabel("记录中")
        self.lbl_status.setStyleSheet(
            f"font-size: 12px; color: {COLORS['success_green']}; font-weight: 700;"
        )
        layout.addWidget(self.lbl_status)
        layout.addSpacing(20)

        self.lbl_time = QLabel()
        self.lbl_time.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']};"
        )
        self.lbl_time.setText(f"🕒 {datetime.now().strftime('%H:%M:%S')}")
        layout.addWidget(self.lbl_time)
        layout.addStretch()

        btn_quit = QPushButton("退出程序")
        btn_quit.setStyleSheet(BUTTON_DANGER_STYLE)
        btn_quit.setCursor(Qt.PointingHandCursor)
        btn_quit.clicked.connect(self._quit_app)
        layout.addWidget(btn_quit)
        return bar

    def _on_nav_changed(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)
            self.lbl_page_title.setText(NAV_ITEMS[row][0])

    def _on_sample(self, sample):
        if self.stack.currentWidget() is self.pages.get("live"):
            self.pages["live"].on_sample_updated(sample)
        self.lbl_time.setText(f"🕒 {datetime.now().strftime('%H:%M:%S')}")

    def _toggle_pause(self):
        if self.worker.is_paused():
            self.worker.resume()
            self.btn_pause.setText("⏸ 暂停")
            self.btn_pause.setStyleSheet(BUTTON_SECONDARY_STYLE)
            self.lbl_status.setText("记录中")
            self.lbl_status.setStyleSheet(
                f"font-size: 12px; color: {COLORS['success_green']}; font-weight: 700;"
            )
            self._status_dot.setStyleSheet(
                f"background: {COLORS['success_green']}; border-radius: 4px;"
            )
        else:
            self.worker.pause()
            self.btn_pause.setText("▶ 继续")
            self.btn_pause.setStyleSheet(BUTTON_PRIMARY_STYLE)
            self.lbl_status.setText("已暂停")
            self.lbl_status.setStyleSheet(
                f"font-size: 12px; color: {COLORS['warning_yellow']}; font-weight: 700;"
            )
            self._status_dot.setStyleSheet(
                f"background: {COLORS['warning_yellow']}; border-radius: 4px;"
            )

    def _update_top_bar(self):
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            totals = stats.get("totals", {})
            effective = totals.get("effective_seconds", 0) or 0
            work_cats = {"ai_tools", "coding", "reading", "creative"}
            work_sec = sum(
                item.get("effective_seconds", 0) or 0
                for item in stats.get("by_category", [])
                if item.get("category_key") in work_cats
            )
            video_sec = sum(
                item.get("effective_seconds", 0) or 0
                for item in stats.get("by_category", [])
                if item.get("category_key") in ("video", "gaming")
            )
            self.top_summary.setText(
                f"总活跃 {fmt_seconds(effective)}  |  学习/工作 {fmt_seconds(work_sec)}  |  娱乐 {fmt_seconds(video_sec)}"
            )
        except Exception as exc:
            import sys
            import traceback

            print(f"[MainWindow] _update_top_bar error: {exc}", file=sys.stderr)
            traceback.print_exc()

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
        except Exception as exc:
            QMessageBox.warning(self, "生成失败", str(exc))

    def _quit_app(self):
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？\n系统托盘图标也会关闭。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if self.worker:
            self.worker.stop()
            self.worker.wait(5000)
        QApplication.instance().quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if hasattr(self, "tray"):
            self.tray.showMessage(
                "Desktop Activity Tracker",
                "程序已最小化到系统托盘。\n右键托盘图标可重新打开。",
            )
