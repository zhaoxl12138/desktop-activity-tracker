"""Main application window with sidebar navigation and dashboard shell."""

from __future__ import annotations

import os
import sys
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
    "WindowsTerminal.exe": "终端",
    "Code.exe": "VS Code",
    "Cursor.exe": "Cursor",
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "QyClient.exe": "爱奇艺",
    "QyPlayer.exe": "爱奇艺",
    "QQ.exe": "QQ",
    "QQLive.exe": "腾讯视频",
    "QQMusic.exe": "QQ音乐",
    "WeChat.exe": "微信",
    "Weixin.exe": "微信",
    "Codex.exe": "Codex",
    "codex.exe": "Codex",
    "Obsidian.exe": "Obsidian",
    "python.exe": "Python",
    "pythonw.exe": "DayLens",
    "DayLens.exe": "DayLens",
    "explorer.exe": "资源管理器",
    "claude.exe": "Claude Code",
}


class MainWindow(QMainWindow):
    FIXED_SIZE = QSize(1600, 960)

    def __init__(self, app_root, config, db_path, config_path, reports_dir, worker):
        super().__init__()
        self.app_root = app_root
        self.config = config
        self.db_path = db_path
        self.config_path = config_path
        self.reports_dir = reports_dir
        self.worker = worker
        self._theme_rebuilding = False
        self._last_sample: dict | None = None
        self.current_theme = ui_style.apply_theme(self.config.get("theme", "dark"))

        self.setWindowTitle("DayLens")
        self.setStyleSheet(ui_style.get_global_style() + ui_style.get_input_style())
        self.setFixedSize(self.FIXED_SIZE)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self._build_ui()
        self._apply_window_chrome_theme()
        self._apply_initial_geometry()

        self.worker.sample_updated.connect(self._on_sample)
        self.nav_list.setCurrentRow(0)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_top_bar)
        self.refresh_timer.start(5000)

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
        current_row = next((index for index, (_, key, _) in enumerate(NAV_ITEMS) if key == current_key), 0)
        self.nav_list.setCurrentRow(current_row)

    def _build_sidebar(self) -> QWidget:
        frame = QFrame()
        frame.setFixedWidth(254)
        frame.setStyleSheet(f"background: {ui_style.COLORS['sidebar_bg']};")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 18, 16, 14)
        layout.setSpacing(0)

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
            item.setSizeHint(QSize(0, 52))
            self.nav_list.addItem(item)
        nav_height = 14 * 2 + len(NAV_ITEMS) * 52 + max(0, len(NAV_ITEMS) - 1) * 2 + 14
        self.nav_list.setFixedHeight(nav_height)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav_list, 1)

        self.chk_dark_mode = QCheckBox("深色模式")
        self.chk_dark_mode.setChecked(ui_style.is_dark_theme())
        self.chk_dark_mode.setStyleSheet(
            f"""
            QCheckBox {{
                color: {ui_style.COLORS['text_secondary']};
                font-size: 14px;
                padding: 10px 2px 18px 2px;
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

        status_card = QFrame()
        status_card.setObjectName("dashboardCard")
        status_card.setStyleSheet(ui_style.get_dashboard_card_style())
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(8)

        self.sidebar_record_status = QLabel("● 记录中")
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 14px; color: {ui_style.COLORS['success_green']}; font-weight: 800;"
        )
        status_layout.addWidget(self.sidebar_record_status)

        self.sidebar_version = QLabel("v1.5.2")
        self.sidebar_version.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']};"
        )
        status_layout.addWidget(self.sidebar_version)

        self.sidebar_sample_time = QLabel(f"最近采样 {datetime.now().strftime('%H:%M:%S')}")
        self.sidebar_sample_time.setStyleSheet(
            f"font-size: 11px; color: {ui_style.COLORS['text_muted']};"
        )
        status_layout.addWidget(self.sidebar_sample_time)
        layout.addWidget(status_card)
        layout.addSpacing(14)

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
            "rules": RuleConfigPage(self.config_path, self.worker),
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
        bar.setFixedHeight(168)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(34, 24, 34, 20)
        layout.setSpacing(24)

        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(8)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        icon_label = QLabel()
        icon_label.setFixedSize(34, 34)
        icon_path = os.path.join(self.app_root, "assets", "icon.ico")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(pixmap)
        brand_row.addWidget(icon_label)

        brand = QLabel("DayLens")
        brand.setStyleSheet(
            f"font-size: 22px; font-weight: 900; color: {ui_style.COLORS['text']};"
        )
        brand_row.addWidget(brand)
        brand_row.addStretch()
        title_wrap.addLayout(brand_row)

        top_line = QHBoxLayout()
        top_line.setSpacing(12)

        self.lbl_page_title = QLabel("今日概览")
        self.lbl_page_title.setStyleSheet(
            f"font-size: 34px; font-weight: 900; color: {ui_style.COLORS['text']};"
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

        self.capsule_values: dict[str, QLabel] = {}
        self.capsule_labels: dict[str, QLabel] = {}
        self.capsule_icons: dict[str, QLabel] = {}
        layout.addStretch()
        layout.addWidget(self._build_summary_capsules())
        layout.addStretch()

        self.btn_pause = QPushButton("暂停记录")
        self.btn_pause.setStyleSheet(ui_style.get_button_secondary_style())
        self.btn_pause.clicked.connect(self._toggle_pause)
        layout.addWidget(self.btn_pause)

        self.btn_report = QPushButton("生成日报")
        self.btn_report.setStyleSheet(ui_style.get_button_primary_style())
        self.btn_report.clicked.connect(self._quick_report)
        layout.addWidget(self.btn_report)

        self._update_top_bar()
        return bar

    def _build_summary_capsules(self) -> QFrame:
        capsule = QFrame()
        capsule.setStyleSheet(
            f"""
            QFrame {{
                background: {ui_style.COLORS['panel_bg']};
                border: 1px solid {ui_style.COLORS['border']};
                border-radius: 18px;
            }}
            """
        )
        layout = QHBoxLayout(capsule)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(20)

        for index, (emoji, label, key) in enumerate(
            [
                ("⚡", "今日活跃", "total"),
                ("💼", "办公", "work"),
                ("🎬", "视频娱乐", "ent"),
                ("💬", "社交通讯", "social"),
            ]
        ):
            item, value_label, icon_label, text_label = self._make_capsule(emoji, label)
            item.setFixedWidth(170)
            layout.addWidget(item)
            self.capsule_values[key] = value_label
            self.capsule_icons[key] = icon_label
            self.capsule_labels[key] = text_label
            if index < 3:
                line = QFrame()
                line.setFixedWidth(1)
                line.setStyleSheet(f"background: {ui_style.COLORS['border']};")
                layout.addWidget(line)
        return capsule

    def _make_capsule(self, emoji: str, label_text: str) -> tuple[QFrame, QLabel, QLabel, QLabel]:
        """Create a capsule-style pill widget like Linear / Raycast / Arc Browser."""
        capsule = QFrame()
        capsule.setStyleSheet(
            f"""
            QFrame {{
                background: transparent;
                border: none;
            }}
            """
        )
        h = QHBoxLayout(capsule)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)

        emoji_lbl = QLabel(emoji)
        emoji_lbl.setStyleSheet("font-size: 24px; background: transparent;")
        h.addWidget(emoji_lbl)

        text_wrap = QVBoxLayout()
        text_wrap.setSpacing(2)
        text_lbl = QLabel(label_text)
        text_lbl.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text']};"
            " font-weight: 700; background: transparent;"
        )
        text_wrap.addWidget(text_lbl)

        value_lbl = QLabel("--")
        value_lbl.setStyleSheet(
            f"font-size: 23px; color: {ui_style.COLORS['text']};"
            " font-weight: 900; background: transparent;"
        )
        text_wrap.addWidget(value_lbl)
        h.addLayout(text_wrap)

        return capsule, value_lbl, emoji_lbl, text_lbl

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

        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _apply_window_chrome_theme(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            is_dark = ui_style.is_dark_theme()
            value = ctypes.c_int(1 if is_dark else 0)
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    wintypes.HWND(hwnd),
                    wintypes.DWORD(attribute),
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                if result == 0:
                    break
            if is_dark:
                caption_color = ctypes.c_int(0x001D0D02)
                text_color = ctypes.c_int(0x00FFFFFF)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    wintypes.HWND(hwnd),
                    wintypes.DWORD(35),
                    ctypes.byref(caption_color),
                    ctypes.sizeof(caption_color),
                )
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    wintypes.HWND(hwnd),
                    wintypes.DWORD(36),
                    ctypes.byref(text_color),
                    ctypes.sizeof(text_color),
                )
        except Exception:
            return

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
                if self._last_sample is not None:
                    if key == "live":
                        self.pages["live"].on_sample_updated(self._last_sample)
                    self.pages["today"].on_sample_updated(self._last_sample)
                break

    def _on_sample(self, sample) -> None:
        self._last_sample = sample
        if self.stack.currentWidget() is self.pages.get("live"):
            self.pages["live"].on_sample_updated(sample)
        self.pages["today"].on_sample_updated(sample)
        self.sidebar_sample_time.setText(f"最近采样 {datetime.now().strftime('%H:%M:%S')}")

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

        self.sidebar_record_status.setText(f"● {text}")
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 14px; color: {color}; font-weight: 800;"
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
        social_seconds = sum(
            item.get("effective_seconds", 0) or 0
            for item in stats.get("by_category", [])
            if item.get("category_key") == "social"
        )
        self.capsule_values["total"].setText(fmt_seconds(effective))
        self.capsule_values["work"].setText(fmt_seconds(work_seconds))
        self.capsule_values["ent"].setText(fmt_seconds(video_seconds))
        self.capsule_values["social"].setText(fmt_seconds(social_seconds))

    def _quick_report(self) -> None:
        from .. import exporter

        today = datetime.now().strftime("%Y-%m-%d")
        daily_dir = os.path.join(self.reports_dir, "daily")
        os.makedirs(daily_dir, exist_ok=True)
        try:
            path = exporter.export_markdown(self.db_path, today, daily_dir)
            obsidian_path = self._live_obsidian_path()
            if obsidian_path:
                synced = exporter.sync_to_obsidian(path, obsidian_path)
                if synced:
                    QMessageBox.information(self, "生成成功", f"日报已保存到\n{path}\n\n已同步到 Obsidian:\n{synced}")
                    return
            QMessageBox.information(self, "生成成功", f"日报已保存到\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "生成失败", str(exc))

    def _live_obsidian_path(self) -> str:
        """Re-read obsidian_output_path from config file, falling back to memory."""
        import yaml
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return (yaml.safe_load(f) or {}).get("obsidian_output_path", "").strip()
        except Exception:
            return self.config.get("obsidian_output_path", "").strip()

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
        self._apply_window_chrome_theme()
        self._update_top_bar()
        if self.worker.is_paused():
            self._toggle_pause()
            self._toggle_pause()
        self._theme_rebuilding = False

    def _persist_theme_preference(self) -> None:
        """Write only the theme key back, preserving the rest of the file."""
        import re

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return

        theme_line = f"theme: {self.current_theme}"
        if re.search(r'^theme:', content, re.MULTILINE):
            content = re.sub(r'^theme:.*$', theme_line, content, flags=re.MULTILINE)
        else:
            content = content.rstrip() + "\n" + theme_line + "\n"

        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Also persist to data/user_config.yaml (survives rebuilds)
        import yaml as _yaml
        from .. import get_data_dir
        user_path = os.path.join(get_data_dir(), "user_config.yaml")
        user_config = {}
        if os.path.exists(user_path):
            try:
                with open(user_path, "r", encoding="utf-8") as f:
                    user_config = _yaml.safe_load(f) or {}
            except Exception:
                pass
        user_config["theme"] = self.current_theme
        os.makedirs(os.path.dirname(user_path), exist_ok=True)
        with open(user_path, "w", encoding="utf-8") as f:
            _yaml.safe_dump(user_config, f, allow_unicode=True)
