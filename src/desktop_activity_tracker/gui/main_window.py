"""Main application window with sidebar navigation and dashboard shell."""

from __future__ import annotations

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
    ("今日概览", "today", "聚焦今天的使用结构、效率与提醒"),
    ("实时监控", "live", "查看当前前台窗口与活动状态"),
    ("软件统计", "software", "分析软件使用时长与占比"),
    ("分类统计", "category", "按分类查看效率结构"),
    ("日报/周报", "reports", "生成日报、周报和月报"),
    ("目标管理", "rules", "管理目标与规则"),
    ("设置中心", "settings", "管理数据库、导出路径与基础参数"),
]

MAIN_NAV_COUNT = 7

DEFAULT_DISPLAY_NAME_MAPPING = {
    "WindowsTerminal.exe": "Windows Terminal",
    "Code.exe": "VS Code",
    "Cursor.exe": "Cursor",
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "QyClient.exe": "QQ",
    "WeChat.exe": "微信",
    "Weixin.exe": "微信",
    "Codex.exe": "Codex",
    "codex.exe": "Codex",
    "Obsidian.exe": "Obsidian",
    "python.exe": "Python",
    "explorer.exe": "资源管理器",
}


class MainWindow(QMainWindow):
    def __init__(self, app_root, config, db_path, config_path, reports_dir, worker):
        super().__init__()
        self.app_root = app_root
        self.config = config
        self.db_path = db_path
        self.config_path = config_path
        self.reports_dir = reports_dir
        self.worker = worker
        self.setWindowTitle("DayLens")
        self.setStyleSheet(GLOBAL_STYLE + INPUT_STYLE)
        self.resize(1440, 860)
        self.setMinimumSize(1280, 780)

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
        layout.setContentsMargins(0, 20, 0, 14)
        brand = QLabel("DayLens")
        brand.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['text_inverse']}; padding: 12px 20px;")
        layout.addWidget(brand)
        tagline = QLabel("Focus · Analyze · Improve")
        tagline.setStyleSheet(f"font-size: 11px; color: {COLORS['text_muted']}; padding: 0 20px 14px 20px;")
        layout.addWidget(tagline)
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #29416F; margin: 0 14px;")
        layout.addWidget(divider)

        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet(SIDEBAR_STYLE)
        self.nav_list.setFont(QFont("Microsoft YaHei", 11))
        for idx, (title, key, hint) in enumerate(NAV_ITEMS):
            if idx == MAIN_NAV_COUNT:
                sep = QListWidgetItem("")
                sep.setFlags(Qt.NoItemFlags)
                sep.setData(Qt.UserRole, {"key": "__separator__"})
                self.nav_list.addItem(sep)
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, {"key": key, "title": title, "hint": hint})
            self.nav_list.addItem(item)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav_list)
        layout.addStretch()
        version = QLabel("v1.4.0")
        version.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']}; padding: 8px 16px;")
        layout.addWidget(version)
        return frame

    def _build_pages(self):
        self.stack = QStackedWidget()
        display_name_mapping = {**DEFAULT_DISPLAY_NAME_MAPPING, **self.config.get("display_name_mapping", {})}
        self.pages = {
            "today": TodayOverviewPage(self.db_path, display_name_mapping),
            "live": LiveMonitorPage(),
            "software": SoftwareStatsPage(self.db_path, self.reports_dir),
            "category": CategoryStatsPage(self.db_path),
        }
        obsidian_path = self.config.get("obsidian_output_path", "").strip()
        self.pages["reports"] = ReportsPage(self.db_path, self.reports_dir, obsidian_path)
        self.pages["rules"] = RuleConfigPage(self.config_path)
        self.pages["settings"] = SettingsPage(self.config_path, self.db_path, self.reports_dir, self.worker)
        for _, key, _ in NAV_ITEMS:
            self.stack.addWidget(self.pages[key])
        return self.stack

    def _build_top_bar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setStyleSheet(TOP_BAR_STYLE)
        bar.setFixedHeight(92)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)
        title_wrap = QVBoxLayout()
        top_line = QHBoxLayout()
        self.lbl_page_title = QLabel("今日概览")
        self.lbl_page_title.setStyleSheet(f"font-size: 38px; font-weight: 800; color: {COLORS['text']};")
        top_line.addWidget(self.lbl_page_title)
        self.lbl_today = QLabel(self._today_text())
        self.lbl_today.setStyleSheet(f"font-size: 15px; color: {COLORS['text_secondary']}; font-weight: 600;")
        top_line.addWidget(self.lbl_today)
        top_line.addStretch()
        title_wrap.addLayout(top_line)
        self.lbl_page_hint = QLabel("聚焦今天的使用结构、效率与提醒")
        self.lbl_page_hint.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        title_wrap.addWidget(self.lbl_page_hint)
        layout.addLayout(title_wrap)
        layout.addStretch()
        self.top_summary = QLabel()
        self.top_summary.setStyleSheet(f"font-size: 14px; color: {COLORS['text_secondary']}; font-weight: 700;")
        self._update_top_bar()
        layout.addWidget(self.top_summary)
        self.btn_pause = QPushButton("⏸ 暂停记录")
        self.btn_pause.setStyleSheet(BUTTON_SECONDARY_STYLE)
        self.btn_pause.clicked.connect(self._toggle_pause)
        layout.addWidget(self.btn_pause)
        btn_report = QPushButton("📄 生成日报")
        btn_report.setStyleSheet(BUTTON_PRIMARY_STYLE)
        btn_report.clicked.connect(self._quick_report)
        layout.addWidget(btn_report)
        return bar

    def _build_bottom_bar(self):
        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar.setStyleSheet(BOTTOM_BAR_STYLE)
        bar.setFixedHeight(38)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(f"font-size: 12px; color: {COLORS['success_green']}; font-weight: 700;")
        layout.addWidget(self._status_dot)
        self.lbl_status = QLabel("记录中")
        self.lbl_status.setStyleSheet(f"font-size: 12px; color: {COLORS['success_green']}; font-weight: 700;")
        layout.addWidget(self.lbl_status)
        layout.addSpacing(16)
        self.lbl_time = QLabel(f"最近采样：{datetime.now().strftime('%H:%M:%S')}")
        self.lbl_time.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(self.lbl_time)
        layout.addStretch()
        btn_quit = QPushButton("退出程序")
        btn_quit.setStyleSheet(BUTTON_DANGER_STYLE)
        btn_quit.clicked.connect(self._quit_app)
        layout.addWidget(btn_quit)
        return bar

    def _today_text(self):
        weekdays = "一二三四五六日"
        now = datetime.now()
        return f"{now.year}年{now.month}月{now.day}日  星期{weekdays[now.weekday()]}"

    def _on_nav_changed(self, row):
        item = self.nav_list.item(row)
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not data or data.get("key") == "__separator__":
            return
        key = data["key"]
        for idx, (_, nav_key, hint) in enumerate(NAV_ITEMS):
            if nav_key == key:
                self.stack.setCurrentIndex(idx)
                self.lbl_page_title.setText(NAV_ITEMS[idx][0])
                self.lbl_page_hint.setText(hint)
                break

    def _on_sample(self, sample):
        if self.stack.currentWidget() is self.pages.get("live"):
            self.pages["live"].on_sample_updated(sample)
        self.lbl_time.setText(f"最近采样：{datetime.now().strftime('%H:%M:%S')}")

    def _toggle_pause(self):
        if self.worker.is_paused():
            self.worker.resume()
            self.btn_pause.setText("⏸ 暂停记录")
            self.btn_pause.setStyleSheet(BUTTON_SECONDARY_STYLE)
            self.lbl_status.setText("记录中")
            color = COLORS["success_green"]
        else:
            self.worker.pause()
            self.btn_pause.setText("▶ 继续记录")
            self.btn_pause.setStyleSheet(BUTTON_PRIMARY_STYLE)
            self.lbl_status.setText("已暂停")
            color = COLORS["warning_yellow"]
        self.lbl_status.setStyleSheet(f"font-size: 12px; color: {color}; font-weight: 700;")
        self._status_dot.setStyleSheet(f"font-size: 12px; color: {color}; font-weight: 700;")

    def _update_top_bar(self):
        self.lbl_today.setText(self._today_text())
        today = datetime.now().strftime("%Y-%m-%d")
        stats = database.query_date_stats(self.db_path, today)
        totals = stats.get("totals", {})
        effective = totals.get("effective_seconds", 0) or 0
        work_keys = {"ai_tools", "coding", "reading", "creative"}
        work_sec = sum((x.get("effective_seconds", 0) or 0) for x in stats.get("by_category", []) if x.get("category_key") in work_keys)
        video_sec = sum((x.get("effective_seconds", 0) or 0) for x in stats.get("by_category", []) if x.get("category_key") in {"video", "gaming"})
        self.top_summary.setText(f"总活跃 {fmt_seconds(effective)}  |  学习/工作 {fmt_seconds(work_sec)}  |  娱乐 {fmt_seconds(video_sec)}")

    def _quick_report(self):
        from .. import exporter

        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.reports_dir, "daily")
        os.makedirs(daily_dir, exist_ok=True)
        try:
            path = exporter.export_markdown(self.db_path, today, daily_dir)
            obsidian_path = self.config.get("obsidian_output_path", "").strip()
            if obsidian_path:
                exporter.sync_to_obsidian(path, obsidian_path)
            QMessageBox.information(self, "生成成功", f"日报已保存到\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "生成失败", str(exc))

    def _quit_app(self):
        reply = QMessageBox.question(self, "确认退出", "确定要退出程序吗？", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        if self.worker:
            self.worker.stop()
            self.worker.wait(5000)
        QApplication.instance().quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
