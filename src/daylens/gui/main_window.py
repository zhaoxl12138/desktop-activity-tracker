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
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..utils import fmt_seconds
from ..services.shell_service import generate_daily_report, load_poetry_hint, load_shell_summary
from ..services.reports_service import (
    auto_generate_daily_report,
    auto_generate_current_reports,
)
from ..services.restart_service import current_launch_command, schedule_restart
from ..services.gui_shutdown_service import stop_recording_worker_safely
from .report_backfill_worker import ReportBackfillWorker
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
    ("规则管理", "rules", "管理分类规则与计时策略"),
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
    FIXED_SIZE = QSize(1600, 900)

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
        self._recording_health = getattr(worker, "health", None)
        self._current_nav_key: str | None = None
        self._last_poetry_refresh = 0.0
        self._poetry_interval = 1800
        self.current_theme = ui_style.apply_theme(self.config.get("theme", "dark"))

        self.setWindowTitle("DayLens")
        self.setStyleSheet(ui_style.get_global_style() + ui_style.get_input_style())
        self.resize(self.FIXED_SIZE)
        self.setMinimumSize(QSize(1100, 700))
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self._init_pages()
        self._build_ui()
        self._apply_window_chrome_theme()
        self._apply_initial_geometry()

        self._connect_recording_worker(self.worker)
        self.nav_list.setCurrentRow(0)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_top_bar)
        self.refresh_timer.start(5000)

        # Auto-generate weekly/monthly reports
        QTimer.singleShot(5000, self._check_report_schedule)
        self.report_schedule_timer = QTimer(self)
        self.report_schedule_timer.timeout.connect(self._check_report_schedule)
        self.report_schedule_timer.start(300000)  # every 5 minutes
        self.daily_report_timer = QTimer(self)
        self.daily_report_timer.timeout.connect(self._auto_generate_daily_report)
        self.daily_report_timer.start(3600000)  # refresh today's report every hour
        QTimer.singleShot(10000, self._auto_generate_daily_report)
        self._report_backfill_worker = None
        QTimer.singleShot(15000, self._start_report_backfill)

    def _init_pages(self) -> None:
        """Create page widgets once. Reused across theme toggles."""
        self.stack = QStackedWidget()
        display_name_mapping = {**DISPLAY_NAME_MAPPING, **self.config.get("display_name_mapping", {})}
        self.pages = {
            "today": TodayOverviewPage(self.db_path, display_name_mapping),
            "live": LiveMonitorPage(),
            "software": SoftwareStatsPage(self.db_path, self.reports_dir, display_name_mapping),
            "category": CategoryStatsPage(self.db_path),
            "reports": ReportsPage(
                self.db_path, self.reports_dir,
                self.config.get("obsidian_output_path", "").strip(),
            ),
            "rules": RuleConfigPage(self.config_path, self.db_path, self.worker),
            "settings": SettingsPage(self.config_path, self.db_path, self.reports_dir, self.worker),
        }
        self.pages["settings"].config_saved.connect(self._apply_saved_config)
        self.pages["settings"].restart_requested.connect(self._restart_app)
        for _, key, _ in NAV_ITEMS:
            self.stack.addWidget(self.pages[key])

    def _build_ui(self, current_key: str = "today") -> None:
        central = QWidget()
        self.setCentralWidget(central)

        self.root_layout = QVBoxLayout(central)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        self._top_bar = self._build_top_bar()
        self.root_layout.addWidget(self._top_bar)

        self._content_layout = QHBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

        self._sidebar = self._build_sidebar()
        self._content_layout.addWidget(self._sidebar)
        self.page_scroll = QScrollArea()
        self.page_scroll.setObjectName("pageScroll")
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.page_scroll.setFrameShape(QFrame.NoFrame)
        self.page_scroll.setWidget(self.stack)
        self._content_layout.addWidget(self.page_scroll, 1)
        self.root_layout.addLayout(self._content_layout, 1)

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
        self.nav_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.nav_list.setSpacing(2)
        self.nav_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        for title, key, hint in NAV_ITEMS:
            item = QListWidgetItem(title)
            item.setData(Qt.UserRole, {"key": key, "title": title, "hint": hint})
            item.setSizeHint(QSize(0, 52))
            self.nav_list.addItem(item)
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

        self.sidebar_record_status = QLabel("🟢 正在记录")
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 14px; color: {ui_style.COLORS['success_green']}; font-weight: 800;"
        )
        status_layout.addWidget(self.sidebar_record_status)

        self.sidebar_record_value = QLabel("已记录：--")
        self.sidebar_record_value.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']}; font-weight: 700;"
        )
        status_layout.addWidget(self.sidebar_record_value)

        self.sidebar_record_streak = QLabel("连续记录：第--天")
        self.sidebar_record_streak.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']}; font-weight: 700;"
        )
        status_layout.addWidget(self.sidebar_record_streak)

        self.sidebar_version = QLabel("v1.5.3")
        self.sidebar_version.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']};"
        )
        status_layout.addWidget(self.sidebar_version)

        self.sidebar_sample_time = QLabel("最后采样：--")
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
        self._update_sidebar_status_card()
        return frame

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setStyleSheet(ui_style.get_top_bar_style())
        bar.setMinimumHeight(140)

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
        self.lbl_page_hint.setWordWrap(True)
        self.lbl_page_hint.setMinimumHeight(42)
        self.lbl_page_hint.setMaximumHeight(56)
        self.lbl_page_hint.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum
        )
        self.lbl_page_hint.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};"
        )
        hint_line = QHBoxLayout()
        hint_line.addWidget(self.lbl_page_hint)
        hint_line.addStretch()
        title_wrap.addLayout(hint_line)
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
                ("⚡", "活跃时间", "total"),
                ("💼", "工作学习", "work"),
                ("📺", "娱乐休闲", "ent"),
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
        previous_key = self._current_nav_key
        if previous_key and previous_key != key:
            previous_page = self.pages.get(previous_key)
            if previous_page is not None and hasattr(previous_page, "deactivate"):
                previous_page.deactivate()
        for index, (title, nav_key, hint) in enumerate(NAV_ITEMS):
            if nav_key == key:
                self.stack.setCurrentIndex(index)
                self.lbl_page_title.setText(title)
                self._current_nav_key = key
                if key == "today":
                    self.pages["today"].activate(force=previous_key != "today")
                    self._set_random_poetry(force=True)
                else:
                    self.lbl_page_hint.setText(hint)
                    page = self.pages.get(key)
                    if page is not None and hasattr(page, "activate"):
                        page.activate(force=previous_key != key)
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
        self._update_sidebar_status_card()

    def _connect_recording_worker(self, worker) -> None:
        worker.sample_updated.connect(self._on_sample)
        health_updated = getattr(worker, "health_updated", None)
        if health_updated is not None:
            health_updated.connect(self._on_recording_health)

    def _on_recording_health(self, health) -> None:
        self._recording_health = health
        self._update_recording_health_ui()

    def _update_recording_health_ui(self) -> None:
        health = getattr(self, "_recording_health", None)
        if health is None:
            return
        status = getattr(health, "status", "starting")
        status_styles = {
            "starting": ("🔵 启动中 (starting)", ui_style.COLORS["primary"]),
            "running": ("🟢 正在记录 (running)", ui_style.COLORS["success_green"]),
            "paused": ("🟡 暂停记录 (paused)", ui_style.COLORS["warning_yellow"]),
            "delayed": ("🟡 写入延迟 (write delayed)", ui_style.COLORS["warning_yellow"]),
            "sample_delayed": (
                "🟡 采样延迟 (sample delayed)",
                ui_style.COLORS["warning_yellow"],
            ),
            "degraded": ("🟠 降级运行 (degraded)", ui_style.COLORS["warning_yellow"]),
            "stopped": ("⚪ 已停止 (stopped)", ui_style.COLORS["text_muted"]),
            "fatal": ("🔴 记录错误 (fatal)", ui_style.COLORS["danger_red"]),
        }
        text, color = status_styles.get(
            status,
            (f"⚪ {status}", ui_style.COLORS["text_muted"]),
        )
        error = str(getattr(health, "error", "") or "").strip()
        if error and status in {"sample_delayed", "degraded", "fatal"}:
            text = f"{text} · {error}"
        self.sidebar_record_status.setText(text)
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 14px; color: {color}; font-weight: 800;"
        )
        last_sample_at = getattr(health, "last_sample_at", None)
        sample_text = (
            last_sample_at.strftime("%H:%M:%S")
            if last_sample_at is not None
            else "--"
        )
        self.sidebar_sample_time.setText(f"最后采样：{sample_text}")

    def _update_sidebar_status_card(self) -> None:
        if not hasattr(self, "sidebar_record_value"):
            return
        today_page = self.pages.get("today")
        totals = getattr(today_page, "last_snapshot_totals", {}) if today_page is not None else {}
        effective_seconds = int((totals or {}).get("effective_seconds", 0) or 0)
        consecutive_days = int(getattr(today_page, "last_consecutive_days", 0) or 0)
        self.sidebar_record_value.setText(
            f"已记录：{fmt_seconds(effective_seconds)}" if effective_seconds > 0 else "已记录：--"
        )
        self.sidebar_record_streak.setText(
            f"连续记录：第{consecutive_days}天" if consecutive_days > 0 else "连续记录：--"
        )
        self.sidebar_version.setText("v1.5.3")
        self._update_recording_health_ui()

    def _toggle_pause(self) -> None:
        if self.worker.is_paused():
            self.worker.resume()
            self.btn_pause.setText("暂停记录")
            self.btn_pause.setStyleSheet(ui_style.get_button_secondary_style())
            text = "正在记录"
            color = ui_style.COLORS["success_green"]
        else:
            self.worker.pause()
            self.btn_pause.setText("继续记录")
            self.btn_pause.setStyleSheet(ui_style.get_button_primary_style())
            text = "暂停记录"
            color = ui_style.COLORS["warning_yellow"]

        prefix = "🟢" if self.worker.is_paused() is False else "🟡"
        self.sidebar_record_status.setText(f"{prefix} {text}")
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 14px; color: {color}; font-weight: 800;"
        )

    def _update_top_bar(self) -> None:
        self.lbl_today.setText(self._today_text())
        today = datetime.now().strftime("%Y-%m-%d")
        today_page = self.pages.get("today")
        if today_page is not None and today_page.last_stats_date == today:
            stats = today_page.last_stats
        else:
            stats = None
        if today_page is not None and today_page.last_stats_date == today and today_page.last_shell_summary:
            summary = today_page.last_shell_summary
        else:
            summary = load_shell_summary(self.db_path, stats)
        self.capsule_values["total"].setText(fmt_seconds(summary["effective_seconds"]))
        self.capsule_values["work"].setText(fmt_seconds(summary["work_seconds"]))
        self.capsule_values["ent"].setText(fmt_seconds(summary["entertainment_seconds"]))
        self.capsule_values["social"].setText(fmt_seconds(summary["social_seconds"]))
        self._update_sidebar_status_card()
        if self._current_nav_key == "today":
            self._set_random_poetry(force=False)

    def _set_random_poetry(self, force: bool = False) -> None:
        """Set lbl_page_hint to two random poetry lines from the database.

        Args:
            force: If True, refresh immediately. If False, only refresh if
                   _poetry_interval seconds have passed since last refresh.
        """
        if not force:
            now = __import__("time").time()
            if now - self._last_poetry_refresh < self._poetry_interval:
                return
            self._last_poetry_refresh = now
        for _title, nav_key, hint in NAV_ITEMS:
            if nav_key == self._current_nav_key:
                self.lbl_page_hint.setText(load_poetry_hint(self.db_path, hint))
                return
        self.lbl_page_hint.setText("聚焦今天的使用结构、效率与提醒")

    def _quick_report(self) -> None:
        daily_dir = os.path.join(self.reports_dir, "daily")
        try:
            path, synced = generate_daily_report(self.db_path, daily_dir, self._live_obsidian_path())
            if synced:
                QMessageBox.information(self, "生成成功", f"日报已保存到\n{path}\n\n已同步到 Obsidian:\n{synced}")
                return
            QMessageBox.information(self, "生成成功", f"日报已保存到\n{path}")
        except Exception as exc:
            QMessageBox.warning(self, "生成失败", str(exc))

    def _check_report_schedule(self):
        """Periodically check if weekly/monthly reports should be auto-generated."""
        try:
            now = __import__("time").time()
            last = getattr(self, '_last_report_gen', 0)
            # Debounce: don't regenerate within 5 minutes
            if now - last < 290:
                return

            self._last_report_gen = now
            generated = auto_generate_current_reports(self.db_path, self.reports_dir)
            if generated:
                obsidian_path = self._live_obsidian_path()
                if obsidian_path:
                    from ..exporter import sync_to_obsidian
                    for filepath in generated:
                        sync_to_obsidian(filepath, obsidian_path)
                import sys
                for fp in generated:
                    print(f"[AutoReport] Generated: {fp}", file=sys.stderr)
        except Exception as e:
            import sys, traceback
            print(f"[AutoReport] Error: {e}", file=sys.stderr)
            traceback.print_exc()

    def _auto_generate_daily_report(self):
        """Refresh today's report hourly without interrupting the GUI."""
        path = auto_generate_daily_report(self.db_path, self.reports_dir)
        if path:
            obsidian_path = self._live_obsidian_path()
            if obsidian_path:
                try:
                    from ..exporter import sync_to_obsidian
                    sync_to_obsidian(path, obsidian_path)
                except Exception as exc:
                    import sys
                    print(f"[AutoReport] Daily Obsidian sync failed: {exc}", file=sys.stderr)

    def _start_report_backfill(self) -> None:
        worker = self._report_backfill_worker
        if worker is not None and worker.isRunning():
            return
        worker = ReportBackfillWorker(
            self.db_path,
            self.reports_dir,
            self._live_obsidian_path(),
            self,
        )
        self._report_backfill_worker = worker
        worker.completed.connect(self._on_report_backfill_completed)
        worker.failed.connect(self._on_report_backfill_failed)
        worker.finished.connect(self._cleanup_report_backfill_worker)
        worker.start()

    def _on_report_backfill_completed(self, result: dict) -> None:
        import sys

        print(
            "[AutoReport] Backfill generated "
            f"{result.get('generated_count', 0)}, "
            f"failed {result.get('failure_count', 0)}",
            file=sys.stderr,
        )

    def _on_report_backfill_failed(self, error: str) -> None:
        import sys

        print(f"[AutoReport] Backfill failed: {error}", file=sys.stderr)

    def _cleanup_report_backfill_worker(self) -> None:
        worker = self._report_backfill_worker
        self._report_backfill_worker = None
        if worker is not None:
            worker.deleteLater()

    def _live_obsidian_path(self) -> str:
        """Return obsidian_output_path from in-memory config (merged with DB on startup)."""
        return self.config.get("obsidian_output_path", "").strip()

    def _apply_saved_config(self, config: dict) -> None:
        self.config = config
        obsidian_path = config.get("obsidian_output_path", "").strip()
        reports_page = self.pages.get("reports")
        if reports_page is not None:
            reports_page.obsidian_path = obsidian_path
        tray = getattr(self, "tray", None)
        if tray is not None:
            tray.config = config

    def _restart_app(self) -> None:
        try:
            command = current_launch_command()
        except Exception as exc:
            QMessageBox.warning(self, "重启失败", str(exc))
            return

        try:
            restart_handle = schedule_restart(command, deferred=True)
        except Exception as exc:
            QMessageBox.warning(self, "重启失败", str(exc))
            return

        result = stop_recording_worker_safely(self.worker)
        if not result.completed:
            restart_handle.cancel()
            QMessageBox.warning(self, "Cannot restart safely", result.message)
            return

        try:
            restart_handle.arm()
        except Exception as exc:
            restart_handle.cancel()
            try:
                self.worker = self._restore_recording_worker()
            except Exception as restore_exc:
                QMessageBox.warning(
                    self,
                    "记录恢复失败",
                    f"{exc}\n\n记录线程恢复失败：{restore_exc}",
                )
                return
            QMessageBox.warning(self, "重启失败", str(exc))
            return

        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _quit_app(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        result = stop_recording_worker_safely(self.worker)
        if not result.completed:
            QMessageBox.warning(self, "Cannot quit safely", result.message)
            return
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _restore_recording_worker(self):
        from .worker import RecordingWorker

        replacement = RecordingWorker(
            self.config_path,
            self.db_path,
            self.config,
        )
        self._connect_recording_worker(replacement)
        self._recording_health = replacement.health
        self._update_recording_health_ui()
        for page_key in ("rules", "settings"):
            page = self.pages.get(page_key)
            if page is not None and hasattr(page, "worker"):
                page.worker = replacement
        replacement.start()
        return replacement

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()

    def _toggle_theme(self, checked: bool) -> None:
        if self._theme_rebuilding:
            return
        self._theme_rebuilding = True
        old_colors = dict(ui_style.COLORS)
        try:
            self.current_theme = ui_style.apply_theme(
                "dark" if checked else "light"
            )
            self.config["theme"] = self.current_theme
            self._persist_theme_preference()
            self.setStyleSheet(
                ui_style.get_global_style() + ui_style.get_input_style()
            )
            self._retarget_inline_theme_colors(old_colors)
            self._apply_window_chrome_theme()
            self._update_top_bar()
            self.update()
        finally:
            self._theme_rebuilding = False

    def _retarget_inline_theme_colors(self, old_colors: dict[str, str]) -> None:
        """Update existing inline QSS without rebuilding stateful page widgets."""
        replacements = {
            old_colors[key]: ui_style.COLORS[key]
            for key in old_colors.keys() & ui_style.COLORS.keys()
            if old_colors[key] != ui_style.COLORS[key]
        }
        for widget in (self, *self.findChildren(QWidget)):
            sheet = widget.styleSheet()
            if not sheet:
                continue
            updated = sheet
            for old_value, new_value in replacements.items():
                updated = updated.replace(old_value, new_value)
            if updated != sheet:
                widget.setStyleSheet(updated)

    def _persist_theme_preference(self) -> None:
        """Persist theme as user state; factory config remains read-only."""
        from ..utils import save_user_config
        save_user_config({"theme": self.current_theme})
