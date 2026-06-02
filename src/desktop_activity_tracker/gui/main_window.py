"""Main application window with sidebar navigation and dashboard shell."""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
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
from . import style as ui_style


NAV_ITEMS = [
    ("今日概览", "today", "聚焦今天的使用结构、效率与提醒"),
    ("实时监控", "live", "查看当前前台窗口与记录状态"),
    ("软件统计", "software", "分析软件使用时长与活跃度"),
    ("分类统计", "category", "查看分类维度的时间分布"),
    ("日报/周报", "reports", "生成日报与周报"),
    ("目标管理", "rules", "管理目标与规则"),
    ("设置中心", "settings", "管理基础配置与数据路径"),
]

DISPLAY_NAME_MAPPING = {
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
        self._theme_rebuilding = False
        self.current_theme = ui_style.apply_theme(self.config.get("theme", "dark"))

        self.setWindowTitle("DayLens")
        self.setStyleSheet(ui_style.get_global_style() + ui_style.get_input_style())
        self.resize(1440, 860)
        self.setMinimumSize(1280, 780)
        self._build_ui()
        self._apply_initial_geometry()

        self.worker.sample_updated.connect(self._on_sample)
        self.nav_list.setCurrentRow(0)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_top_bar)
        self.refresh_timer.start(30000)

    def _build_ui(self, current_key: str = "today") -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_top_bar())

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_sidebar())
        content_layout.addWidget(self._build_pages(), 1)
        root_layout.addLayout(content_layout, 1)

        root_layout.addWidget(self._build_bottom_bar())
        current_row = next((index for index, (_, key, _) in enumerate(NAV_ITEMS) if key == current_key), 0)
        self.nav_list.setCurrentRow(current_row)

    def _build_sidebar(self) -> QWidget:
        frame = QFrame()
        frame.setFixedWidth(236)
        frame.setStyleSheet(f"background: {ui_style.COLORS['sidebar_bg']};")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 20, 0, 14)
        layout.setSpacing(0)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(20, 12, 20, 8)
        brand_row.setSpacing(12)

        icon_label = QLabel()
        icon_label.setFixedSize(34, 34)
        icon_path = os.path.join(self.app_root, "assets", "icon.ico")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(pixmap)
        brand_row.addWidget(icon_label)

        brand = QLabel("DayLens")
        brand.setStyleSheet(
            f"font-size: 20px; font-weight: 800; color: {ui_style.COLORS['text_inverse']};"
        )
        brand_row.addWidget(brand)
        brand_row.addStretch()
        layout.addLayout(brand_row)

        tagline = QLabel("Focus · Analyze · Improve")
        tagline.setStyleSheet(
            f"font-size: 11px; color: {ui_style.COLORS['text_muted']}; padding: 0 20px 14px 66px;"
        )
        layout.addWidget(tagline)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #29416F; margin: 0 14px;")
        layout.addWidget(divider)

        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet(ui_style.get_sidebar_style())
        self.nav_list.setFont(QFont("Microsoft YaHei", 11))
        self.nav_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav_list.setSpacing(2)
        self.nav_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        for title, key, hint in NAV_ITEMS:
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, {"key": key, "title": title, "hint": hint})
            item.setSizeHint(QSize(0, 44))
            self.nav_list.addItem(item)
        nav_height = 14 * 2 + len(NAV_ITEMS) * 44 + max(0, len(NAV_ITEMS) - 1) * 2 + 14
        self.nav_list.setFixedHeight(nav_height)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav_list, 1)

        other_title = QLabel("其他")
        other_title.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']}; padding: 10px 18px 4px 18px; font-weight: 700;"
        )
        layout.addWidget(other_title)

        self.chk_dark_mode = QCheckBox("深色模式")
        self.chk_dark_mode.setChecked(ui_style.is_dark_theme())
        self.chk_dark_mode.setStyleSheet(
            f"""
            QCheckBox {{
                color: {ui_style.COLORS['text_secondary']};
                font-size: 14px;
                padding: 4px 18px 8px 18px;
            }}
            QCheckBox::indicator {{
                width: 34px;
                height: 18px;
                border-radius: 9px;
                background: {ui_style.COLORS['panel_bg']};
                border: 1px solid {ui_style.COLORS['border']};
            }}
            QCheckBox::indicator:checked {{
                background: {ui_style.COLORS['primary']};
                border: 1px solid {ui_style.COLORS['primary']};
            }}
            """
        )
        self.chk_dark_mode.clicked.connect(self._toggle_theme)
        layout.addWidget(self.chk_dark_mode)

        layout.addStretch()

        self.sidebar_version = QLabel("v1.4.0")
        self.sidebar_version.setStyleSheet(
            f"font-size: 10px; color: {ui_style.COLORS['text_muted']}; padding: 4px 16px;"
        )
        layout.addWidget(self.sidebar_version)

        self.sidebar_record_status = QLabel("● 记录中")
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['success_green']}; font-weight: 700; padding: 2px 16px 8px 16px;"
        )
        layout.addWidget(self.sidebar_record_status)

        self.sidebar_quit_btn = QPushButton("退出程序")
        self.sidebar_quit_btn.setStyleSheet(ui_style.get_button_danger_style())
        self.sidebar_quit_btn.clicked.connect(self._quit_app)
        layout.addWidget(self.sidebar_quit_btn)
        return frame

    def _build_pages(self) -> QWidget:
        self.stack = QStackedWidget()
        display_name_mapping = {**DISPLAY_NAME_MAPPING, **self.config.get("display_name_mapping", {})}
        self.pages = {
            "today": TodayOverviewPage(self.db_path, display_name_mapping),
            "live": LiveMonitorPage(),
            "software": SoftwareStatsPage(self.db_path, self.reports_dir),
            "category": CategoryStatsPage(self.db_path),
            "reports": ReportsPage(
                self.db_path,
                self.reports_dir,
                self.config.get("obsidian_output_path", "").strip(),
            ),
            "rules": RuleConfigPage(self.config_path),
            "settings": SettingsPage(
                self.config_path,
                self.db_path,
                self.reports_dir,
                self.worker,
            ),
        }
        for _, key, _ in NAV_ITEMS:
            self.stack.addWidget(self.pages[key])
        return self.stack

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setStyleSheet(ui_style.get_top_bar_style())
        bar.setFixedHeight(84)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(12)

        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(4)

        top_line = QHBoxLayout()
        top_line.setSpacing(12)

        self.lbl_page_title = QLabel("今日概览")
        self.lbl_page_title.setStyleSheet(
            f"font-size: 32px; font-weight: 800; color: {ui_style.COLORS['text']};"
        )
        top_line.addWidget(self.lbl_page_title)

        self.lbl_today = QLabel(self._today_text())
        self.lbl_today.setStyleSheet(
            f"font-size: 14px; color: {ui_style.COLORS['text_secondary']}; font-weight: 600;"
        )
        top_line.addWidget(self.lbl_today)
        top_line.addStretch()
        title_wrap.addLayout(top_line)

        self.lbl_page_hint = QLabel("聚焦今天的使用结构、效率与提醒")
        self.lbl_page_hint.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};"
        )
        title_wrap.addWidget(self.lbl_page_hint)
        layout.addLayout(title_wrap)

        layout.addStretch()

        self.top_summary = QLabel()
        self.top_summary.setStyleSheet(
            f"font-size: 13px; color: {ui_style.COLORS['text_secondary']}; font-weight: 700;"
        )
        self._update_top_bar()
        layout.addWidget(self.top_summary)

        self.btn_pause = QPushButton("暂停记录")
        self.btn_pause.setStyleSheet(ui_style.get_button_secondary_style())
        self.btn_pause.clicked.connect(self._toggle_pause)
        layout.addWidget(self.btn_pause)

        self.btn_report = QPushButton("生成日报")
        self.btn_report.setStyleSheet(ui_style.get_button_primary_style())
        self.btn_report.clicked.connect(self._quick_report)
        layout.addWidget(self.btn_report)
        return bar

    def _build_bottom_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar.setStyleSheet(ui_style.get_bottom_bar_style())
        bar.setFixedHeight(38)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)
        layout.setSpacing(8)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['success_green']}; font-weight: 700;"
        )
        layout.addWidget(self._status_dot)

        self.lbl_status = QLabel("记录中")
        self.lbl_status.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['success_green']}; font-weight: 700;"
        )
        layout.addWidget(self.lbl_status)

        layout.addSpacing(16)
        self.lbl_time = QLabel(f"最近采样：{datetime.now().strftime('%H:%M:%S')}")
        self.lbl_time.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_muted']};")
        layout.addWidget(self.lbl_time)
        layout.addStretch()
        return bar

    def _apply_initial_geometry(self) -> None:
        available = self.screen().availableGeometry() if self.screen() else None
        if available is None:
            return

        target_width = min(1440, max(1280, available.width() - 80))
        target_height = min(860, max(780, available.height() - 80))
        target_width = min(target_width, available.width())
        target_height = min(target_height, available.height())

        self.resize(target_width, target_height)
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _today_text(self) -> str:
        weekdays = "一二三四五六日"
        now = datetime.now()
        return f"{now.year}年{now.month}月{now.day}日  星期{weekdays[now.weekday()]}"

    def _on_nav_changed(self, row: int) -> None:
        item = self.nav_list.item(row)
        if item is None:
            return
        data = item.data(Qt.UserRole) or {}
        key = data.get("key")
        if not key:
            return
        for index, (title, nav_key, hint) in enumerate(NAV_ITEMS):
            if nav_key == key:
                self.stack.setCurrentIndex(index)
                self.lbl_page_title.setText(title)
                self.lbl_page_hint.setText(hint)
                break

    def _on_sample(self, sample) -> None:
        if self.stack.currentWidget() is self.pages.get("live"):
            self.pages["live"].on_sample_updated(sample)
        self.lbl_time.setText(f"最近采样：{datetime.now().strftime('%H:%M:%S')}")

    def _toggle_pause(self) -> None:
        if self.worker.is_paused():
            self.worker.resume()
            self.btn_pause.setText("暂停记录")
            self.btn_pause.setStyleSheet(ui_style.get_button_secondary_style())
            text = "记录中"
            color = ui_style.COLORS["success_green"]
        else:
            self.worker.pause()
            self.btn_pause.setText("继续记录")
            self.btn_pause.setStyleSheet(ui_style.get_button_primary_style())
            text = "已暂停"
            color = ui_style.COLORS["warning_yellow"]

        self.lbl_status.setText(text)
        self.lbl_status.setStyleSheet(
            f"font-size: 12px; color: {color}; font-weight: 700;"
        )
        self._status_dot.setStyleSheet(
            f"font-size: 12px; color: {color}; font-weight: 700;"
        )
        self.sidebar_record_status.setText(f"● {text}")
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 12px; color: {color}; font-weight: 700; padding: 2px 16px 8px 16px;"
        )

    def _update_top_bar(self) -> None:
        self.lbl_today.setText(self._today_text())
        today = datetime.now().strftime("%Y-%m-%d")
        stats = database.query_date_stats(self.db_path, today)
        totals = stats.get("totals", {})
        effective = totals.get("effective_seconds", 0) or 0
        work_keys = {"ai_tools", "coding", "reading", "creative"}
        work_seconds = sum(
            item.get("effective_seconds", 0) or 0
            for item in stats.get("by_category", [])
            if item.get("category_key") in work_keys
        )
        video_seconds = sum(
            item.get("effective_seconds", 0) or 0
            for item in stats.get("by_category", [])
            if item.get("category_key") in {"video", "gaming"}
        )
        self.top_summary.setText(
            f"总活跃 {fmt_seconds(effective)}  |  学习/工作 {fmt_seconds(work_seconds)}  |  娱乐 {fmt_seconds(video_seconds)}"
        )

    def _quick_report(self) -> None:
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

    def _quit_app(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if self.worker:
            self.worker.stop()
            self.worker.wait(5000)
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()

    def _toggle_theme(self, checked: bool) -> None:
        if self._theme_rebuilding:
            return
        self._theme_rebuilding = True
        self.current_theme = ui_style.apply_theme("dark" if checked else "light")
        self.config["theme"] = self.current_theme
        self._persist_theme_preference()
        current_key = NAV_ITEMS[self.nav_list.currentRow()][1] if self.nav_list.currentRow() >= 0 else "today"
        self.setStyleSheet(ui_style.get_global_style() + ui_style.get_input_style())
        self._build_ui(current_key)
        self._update_top_bar()
        if self.worker.is_paused():
            self._toggle_pause()
            self._toggle_pause()
        self._theme_rebuilding = False

    def _persist_theme_preference(self) -> None:
        import yaml

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                latest_config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            latest_config = {}

        latest_config["theme"] = self.current_theme
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(latest_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
