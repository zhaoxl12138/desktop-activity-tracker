"""Main application window with sidebar navigation and dashboard shell."""

from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QCheckBox,
    QFrame,
    QGridLayout,
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
from ..services.dashboard_service import load_today_snapshot, resolve_display_name
from ..services.daily_observation import (
    candidate_observations,
    generate_daily_observation,
    load_daily_observation,
)
from ..services.intelligence_state import load_settings as load_intelligence_settings
from ..services.reports_service import (
    ReportJob,
    execute_report_job,
)
from ..services.restart_service import current_launch_command, schedule_restart
from ..services.gui_shutdown_service import stop_recording_worker_safely
from ..services.maintenance_control import consume_request as consume_maintenance_request
from ..services.maintenance_control import record_result as record_maintenance_result
from .dashboard_refresh_controller import (
    DashboardRefreshController,
    DashboardSnapshot,
)
from .background_task_queue import BackgroundTaskQueue
from .pages.category_stats import CategoryStatsPage
from .pages.live_monitor import LiveMonitorPage
from .pages.reports import ReportsPage
from .pages.rule_config import RuleConfigPage
from .pages.settings import SettingsPage
from .pages.software_stats import SoftwareStatsPage
from .pages.statistics import StatisticsPage
from .pages.daily_goals import DailyGoalsPage
from .pages.today_overview import TodayOverviewPage
from .widgets.elided_label import ElidedLabel
from .widgets.day_activity_dialog import DayActivityDialog
from .widgets.ui_primitives import PageHeader, StatusBadge
from . import style as ui_style


NAV_ITEMS = [
    ("今日概览", "today", "今天的活动结构与节奏"),
    ("数据统计", "stats", "导出、统计、目标与实时记录"),
    ("分类管理", "rules", "待确认、人工纠错与本地规则"),
    ("报告中心", "reports", "查看日报、周报与月报"),
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
        from ..app_paths import AppPaths
        self.paths = getattr(worker, 'paths', None) or AppPaths.from_database(db_path, program_dir=app_root, reports_dir=reports_dir)
        self._theme_rebuilding = False
        self._last_sample: dict | None = None
        self._sample_revision = 0
        self._live_sample_revision = -1
        self._recording_health = getattr(worker, "health", None)
        self._current_nav_key: str | None = None
        self._stats_navigation_override: str | None = None
        self._dashboard_snapshot: DashboardSnapshot | None = None
        self._day_activity_dialog = None
        self.current_theme = ui_style.apply_theme(self.config.get("theme", "dark"))
        self.background_tasks = BackgroundTaskQueue(parent=self)
        self.background_tasks.task_completed.connect(
            self._on_background_task_completed
        )
        self.background_tasks.task_failed.connect(self._on_background_task_failed)

        self.setWindowTitle("DayLens")
        self.setStyleSheet(ui_style.get_global_style() + ui_style.get_input_style())
        self.resize(self.FIXED_SIZE)
        # Keep the shell usable on a 1280x720 display at 150% scaling
        # (roughly 853x480 logical pixels). Pages already scroll vertically.
        self.setMinimumSize(QSize(720, 440))
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self._init_pages()
        self._build_ui()
        dashboard_mapping = dict(self.display_name_mapping)
        dashboard_db_path = self.db_path
        self.dashboard_refresh = DashboardRefreshController(
            lambda: load_today_snapshot(
                dashboard_db_path,
                lambda process_name, app_details: resolve_display_name(
                    process_name,
                    app_details,
                    dashboard_mapping,
                ),
                self.config,
            ),
            parent=self,
        )
        self.dashboard_refresh.snapshot_ready.connect(
            self._on_dashboard_snapshot
        )
        self.dashboard_refresh.failed.connect(self._on_dashboard_refresh_failed)
        self._apply_window_chrome_theme()
        self._apply_initial_geometry()
        self._update_responsive_top_bar()

        self._connect_recording_worker(self.worker)
        self.nav_list.setCurrentRow(0)

        # Auto-generate weekly/monthly reports
        QTimer.singleShot(5000, self._check_report_schedule)
        self.report_schedule_timer = QTimer(self)
        self.report_schedule_timer.timeout.connect(self._check_report_schedule)
        self.report_schedule_timer.start(60000)  # check the 23:00 boundary each minute
        self.daily_report_timer = QTimer(self)
        self.daily_report_timer.timeout.connect(self._auto_generate_daily_report)
        self.daily_report_timer.start(3600000)  # refresh today's report every hour
        QTimer.singleShot(10000, self._auto_generate_daily_report)
        QTimer.singleShot(15000, self._start_report_backfill)
        self.maintenance_timer = QTimer(self)
        self.maintenance_timer.timeout.connect(self._check_maintenance_request)
        self.maintenance_timer.start(1000)

    def _init_pages(self) -> None:
        """Create page widgets once. Reused across theme toggles."""
        self.stack = QStackedWidget()
        display_name_mapping = {
            **DISPLAY_NAME_MAPPING,
            **self.config.get("display_name_mapping", {}),
        }
        self.display_name_mapping = display_name_mapping
        self.pages = {
            "today": TodayOverviewPage(self.db_path, display_name_mapping),
            "live": LiveMonitorPage(paths=self.paths, categories=self.config.get('categories', {})),
            "software": SoftwareStatsPage(self.db_path, self.reports_dir, display_name_mapping),
            "category": CategoryStatsPage(self.db_path),
            "reports": ReportsPage(
                self.db_path, self.reports_dir,
                self.config.get("obsidian_output_path", "").strip(),
                paths=self.paths,
            ),
            "rules": RuleConfigPage(
                self.config_path,
                self.db_path,
                self.worker,
                self.background_tasks,
            ),
            "settings": SettingsPage(
                self.config_path,
                self.db_path,
                self.reports_dir,
                self.worker,
                self.background_tasks,
                paths=self.paths,
            ),
        }
        self.pages["goals"] = DailyGoalsPage(self.paths.intelligence_dir)
        self.pages["stats"] = StatisticsPage(
            self.pages["software"], self.pages["category"],
            self.pages["goals"], live_page=self.pages["live"]
        )
        self.pages["stats"].tabs.currentChanged.connect(self._sync_statistics_header)
        self.pages["today"].top_app_card.activated.connect(
            lambda: self.navigate_to("stats", tab="software")
        )
        self.pages["today"].day_activity_requested.connect(self._open_day_activity)
        self.pages["goals"].refresh_requested.connect(
            lambda day: self._request_goal_day(day, force=True)
        )
        from .pages.classification_management import ClassificationManagementPage
        live = self.pages['live']
        self.pages['rules'] = ClassificationManagementPage(live, self.pages['rules'])
        live.manage_patterns_button.clicked.disconnect()
        live.manage_patterns_button.setText('打开分类管理')
        live.manage_patterns_button.clicked.connect(lambda: self.nav_list.setCurrentRow(
            next(i for i, item in enumerate(NAV_ITEMS) if item[1]=='rules')))
        self.pages["settings"].config_saved.connect(self._apply_saved_config)
        if callable(getattr(self.worker, 'reload_intelligence', None)):
            self.pages['live'].classification_corrected.connect(
                lambda: self.worker.reload_intelligence())
        live.classification_history_changed.connect(
            self._on_classification_history_changed
        )
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
        self.page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.page_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.page_scroll.setFrameShape(QFrame.NoFrame)
        self.page_scroll.setWidget(self.stack)
        self._content_layout.addWidget(self.page_scroll, 1)
        self.root_layout.addLayout(self._content_layout, 1)

        current_row = next((index for index, (_, key, _) in enumerate(NAV_ITEMS) if key == current_key), 0)
        self.nav_list.setCurrentRow(current_row)

    def _build_sidebar(self) -> QWidget:
        frame = QFrame()
        frame.setFixedWidth(176)
        frame.setStyleSheet(f"background: {ui_style.COLORS['sidebar_bg']};")

        layout = QVBoxLayout(frame)
        self._sidebar_layout = layout
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

        self.sidebar_record_status = QLabel("记录中")
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 13px; color: {ui_style.COLORS['success_green']}; font-weight: 600;"
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
        self.sidebar_status_card = status_card
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
        bar.setMinimumHeight(92)
        bar.setMaximumHeight(112)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(18)

        icon_label = QLabel()
        icon_label.setFixedSize(30, 30)
        icon_path = os.path.join(self.app_root, "assets", "icon.ico")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(pixmap)
        layout.addWidget(icon_label)

        self._page_header = PageHeader("今日概览", self._today_text())
        self.lbl_page_title = self._page_header.title_label
        self.lbl_today = self._page_header.subtitle_label
        layout.addWidget(self._page_header, 1)

        self.lbl_page_hint = ElidedLabel("", max_lines=1)
        self.lbl_page_hint.setTextFormat(Qt.PlainText)
        self.lbl_page_hint.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};"
        )
        self._page_header.layout().addWidget(self.lbl_page_hint)
        self.lbl_page_hint.hide()

        self.capsule_values: dict[str, QLabel] = {}
        self.capsule_labels: dict[str, QLabel] = {}
        self.capsule_icons: dict[str, QLabel] = {}
        self._summary_capsule = self._build_summary_capsules()
        layout.addWidget(self._summary_capsule)

        self.top_data_status = StatusBadge("", "neutral")
        self.top_data_status.hide()
        layout.addWidget(self.top_data_status, 0, Qt.AlignVCenter)

        self.btn_pause = QPushButton("暂停记录")
        self.btn_pause.setStyleSheet(ui_style.get_button_secondary_style())
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_pause.setFixedHeight(44)
        self._top_action_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self._top_action_layout.setSpacing(10)
        self._top_action_layout.addWidget(self.btn_pause)
        layout.addLayout(self._top_action_layout)

        self._update_top_bar()
        return bar

    def _build_summary_capsules(self) -> QFrame:
        capsule = QFrame()
        capsule.setStyleSheet(
            f"""
            QFrame {{
                background: {ui_style.COLORS['panel_bg']};
                border: 1px solid {ui_style.COLORS['border']};
                border-radius: 10px;
            }}
            """
        )
        layout = QGridLayout(capsule)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setHorizontalSpacing(0)
        layout.setVerticalSpacing(0)
        self._summary_capsule_grid = layout
        self.summary_capsule_items: list[QFrame] = []
        item, value_label, icon_label, text_label = self._make_capsule("", "有效活动")
        item.setMinimumWidth(118)
        layout.addWidget(item, 0, 0)
        self.summary_capsule_items.append(item)
        self.capsule_values["total"] = value_label
        self.capsule_icons["total"] = icon_label
        self.capsule_labels["total"] = text_label
        self.top_record_status = StatusBadge("待恢复", "neutral", inline=True)
        self.top_record_status.setFixedHeight(30)
        self.top_record_status.setMinimumWidth(82)
        layout.addWidget(self.top_record_status, 0, 1, Qt.AlignVCenter)
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
        h = QVBoxLayout(capsule)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(1)
        h.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        emoji_lbl = QLabel(emoji)
        emoji_lbl.hide()

        text_lbl = QLabel(label_text)
        text_lbl.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};"
            " font-weight: 700; background: transparent;"
        )
        h.addWidget(text_lbl)

        value_lbl = QLabel("--")
        value_lbl.setStyleSheet(
            f"font-size: 20px; color: {ui_style.COLORS['text']};"
            " font-weight: 900; background: transparent;"
        )
        value_lbl.setMinimumHeight(24)
        h.addWidget(value_lbl)

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

        target_width = min(
            self.FIXED_SIZE.width(),
            max(self.minimumWidth(), int(available.width() * 0.95)),
        )
        target_height = min(
            self.FIXED_SIZE.height(),
            max(self.minimumHeight(), int(available.height() * 0.95)),
        )
        self.resize(target_width, target_height)
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def _update_responsive_top_bar(self) -> None:
        if not hasattr(self, "_summary_capsule_grid"):
            return
        compact = self.width() < 1150
        self._top_bar_compact = compact
        self._top_action_layout.setDirection(
            QBoxLayout.LeftToRight
        )
        # Decide against the logical content width the expanded sidebar would
        # leave.  This avoids keeping a wide sidebar when it would force the
        # dashboard itself into the compact range.
        sidebar_compact = (self.width() - 176) < 1150
        self._sidebar.setFixedWidth(64 if sidebar_compact else 176)
        self._sidebar_layout.setContentsMargins(
            4 if sidebar_compact else 16,
            12 if sidebar_compact else 18,
            4 if sidebar_compact else 16,
            10 if sidebar_compact else 14,
        )
        if sidebar_compact:
            self.nav_list.setStyleSheet(
                f"QListWidget {{ background: transparent; border: none; outline: none; padding: 2px; "
                f"color: {ui_style.COLORS['text_secondary']}; }} "
                "QListWidget::item { height: 46px; padding: 0; margin: 3px 0; border-radius: 9px; "
                f"color: {ui_style.COLORS['text_secondary']}; font-weight: 700; }} "
                f"QListWidget::item:hover {{ background: {ui_style.COLORS['sidebar_hover']}; color: white; }} "
                f"QListWidget::item:selected {{ background: {ui_style.COLORS['sidebar_active']}; color: white; "
                "border: 1px solid #6EA8FF; }"
            )
            self.nav_list.setFont(QFont("Microsoft YaHei", 9))
        else:
            self.nav_list.setStyleSheet(ui_style.get_sidebar_style())
            self.nav_list.setFont(QFont("Microsoft YaHei", 11))
        for index in range(self.nav_list.count()):
            item = self.nav_list.item(index)
            data = item.data(Qt.UserRole) or {}
            title = str(data.get("title", ""))
            item.setText(title[:2] if sidebar_compact else title)
            item.setTextAlignment(
                Qt.AlignCenter if sidebar_compact else (Qt.AlignLeft | Qt.AlignVCenter)
            )
            item.setToolTip(title if sidebar_compact else str(data.get("hint", "")))
        self.chk_dark_mode.setVisible(not sidebar_compact)
        self.sidebar_status_card.setVisible(not sidebar_compact)
        for widget in (
            self.sidebar_record_value,
            self.sidebar_record_streak,
            self.sidebar_version,
            self.sidebar_sample_time,
            self.sidebar_quit_btn,
        ):
            widget.setVisible(not sidebar_compact)
        content_width = max(0, self.width() - self._sidebar.width())
        today_page = self.pages.get("today")
        if today_page is not None and hasattr(today_page, "set_content_width"):
            today_page.set_content_width(content_width)

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
        if key == "stats" and previous_key != "stats":
            self.pages["stats"].select_tab(self._stats_navigation_override or "live")
        if previous_key and previous_key != key:
            previous_page = self.pages.get(previous_key)
            if previous_page is not None and hasattr(previous_page, "deactivate"):
                previous_page.deactivate()
        for index, (title, nav_key, hint) in enumerate(NAV_ITEMS):
            if nav_key == key:
                self.stack.setCurrentIndex(index)
                self.lbl_page_title.setText(title)
                self.lbl_today.setText(self._today_text() if key == "today" else hint)
                self._summary_capsule.show()
                for summary_item in self.summary_capsule_items:
                    summary_item.setVisible(key == "today")
                self._current_nav_key = key
                if key == "stats":
                    self._sync_statistics_header()
                if key == "today":
                    self.pages["today"].activate(force=previous_key != "today")
                    self._show_daily_observation()
                else:
                    self.lbl_page_hint.hide()
                    page = self.pages.get(key)
                    if page is not None and hasattr(page, "activate"):
                        page.activate(force=previous_key != key)
                if self._last_sample is not None:
                    self.pages["today"].on_sample_updated(self._last_sample)
                break

    def _sync_statistics_header(self, _index: int | None = None) -> None:
        if self._current_nav_key != "stats":
            return
        stats = self.pages["stats"]
        if stats.tabs.currentWidget() is self.pages["goals"]:
            self.lbl_page_title.setText("设置目标")
            self.lbl_today.setText("管理每天的投入与产出")
        elif stats.tabs.currentWidget() is self.pages["live"]:
            self.lbl_page_title.setText("实时监控")
            self.lbl_today.setText("诊断当前窗口与记录状态")
            self._deliver_live_sample()
        else:
            self.lbl_page_title.setText("数据统计")
            self.lbl_today.setText("按软件或分类查看时间统计")

    def navigate_to(self, key: str, *, tab: str | None = None) -> None:
        """Navigate by stable page key; optional tab keeps callers index-free."""
        if key in {"software", "category", "live"}:
            tab = key
            key = "stats"
        if key == "stats" and tab:
            self.pages["stats"].select_tab(tab)
        row = next(
            (index for index, (_title, nav_key, _hint) in enumerate(NAV_ITEMS) if nav_key == key),
            -1,
        )
        if row >= 0:
            self._stats_navigation_override = tab if key == "stats" else None
            try:
                self.nav_list.setCurrentRow(row)
            finally:
                self._stats_navigation_override = None

    def _on_sample(self, sample) -> None:
        self._last_sample = sample
        self._sample_revision += 1
        if (self._current_nav_key == "stats"
                and self.pages["stats"].tabs.currentWidget() is self.pages.get("live")):
            self._deliver_live_sample()
        self.pages["today"].on_sample_updated(sample)
        self._update_sidebar_status_card()

    def _on_classification_history_changed(self, result: object) -> None:
        payload = result if isinstance(result, dict) else {}
        if payload.get('rule_changed') and not payload.get('classifier_reloaded'):
            reload_classifier = getattr(self.worker, 'reload_classifier', None)
            if callable(reload_classifier):
                reload_classifier()
            rules_page = self.pages.get('rules')
            editor = getattr(rules_page, 'rules_editor', None)
            reload_rules = getattr(editor, 'reload_from_storage', None)
            if callable(reload_rules):
                reload_rules()

        refresh = getattr(self, 'dashboard_refresh', None)
        invalidate = getattr(refresh, 'invalidate_context', None)
        if callable(invalidate):
            invalidate()
        for key in ('software', 'category'):
            page = self.pages.get(key)
            controller = getattr(page, '_refresh_controller', None)
            invalidate = getattr(controller, 'invalidate_context', None)
            if callable(invalidate):
                invalidate()

    def _deliver_live_sample(self) -> None:
        if self._last_sample is not None and self._live_sample_revision != self._sample_revision:
            self.pages["live"].on_sample_updated(self._last_sample)
            self._live_sample_revision = self._sample_revision

    def _connect_recording_worker(self, worker) -> None:
        worker.sample_updated.connect(self._on_sample)
        history_changed = getattr(
            worker, 'classification_history_changed', None
        )
        if history_changed is not None:
            history_changed.connect(self._on_classification_history_changed)
        applied = getattr(worker, 'classification_applied', None)
        if applied is not None:
            applied.connect(self.pages['live'].on_classification_applied)
            applied.connect(self.pages['rules'].on_classification_applied)
        health_updated = getattr(worker, "health_updated", None)
        if health_updated is not None:
            health_updated.connect(self._on_recording_health)

    def _on_recording_health(self, health) -> None:
        self._recording_health = health
        self._update_recording_health_ui()

    def _show_daily_observation(self) -> None:
        label = getattr(self, "lbl_page_hint", None)
        if label is None:
            return
        if self._current_nav_key != "today":
            label.hide()
            return
        snapshot = getattr(self, "_dashboard_snapshot", None)
        payload = getattr(snapshot, "payload", None)
        day = payload.get("today") if isinstance(payload, dict) else None
        if day != datetime.now().date().isoformat():
            label.hide()
            return
        observation = load_daily_observation(self.paths.intelligence_dir, day)
        if observation is None:
            label.hide()
            return
        as_of = observation.get("as_of")
        prefix = f"AI观察 · 截至{as_of}" if isinstance(as_of, str) and len(as_of) == 5 else "AI观察"
        full_text = f"{prefix} · {observation['text']}"
        label.setText(full_text)
        label.setPersistentToolTip(f"{full_text}\n由今日汇总数据生成；仅作为观察，不代表工作质量评价")
        label.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};"
        )
        label.show()

    def _maybe_generate_daily_observation(self, payload: dict) -> None:
        day = payload.get("today")
        if day != datetime.now().date().isoformat():
            return
        settings = load_intelligence_settings(self.paths.intelligence_dir)
        if not settings["enabled"] or not settings["reports_enabled"]:
            return
        if load_daily_observation(self.paths.intelligence_dir, day) is not None:
            return
        if not candidate_observations(payload):
            return
        directory = self.paths.intelligence_dir
        self.background_tasks.submit(
            f"observation:{day}",
            lambda: generate_daily_observation(directory, payload),
        )

    def _update_recording_health_ui(self) -> None:
        health = getattr(self, "_recording_health", None)
        if health is None:
            return
        status = getattr(health, "status", "starting")
        status_styles = {
            "starting": ("待恢复", ui_style.COLORS["primary"]),
            "running": ("记录中", ui_style.COLORS["success_green"]),
            "paused": ("已暂停", ui_style.COLORS["warning_yellow"]),
            "delayed": ("正在保存", ui_style.COLORS["warning_yellow"]),
            "sample_delayed": ("待恢复", ui_style.COLORS["warning_yellow"]),
            "degraded": ("待恢复", ui_style.COLORS["warning_yellow"]),
            "stopped": ("待恢复", ui_style.COLORS["text_muted"]),
            "fatal": ("记录异常", ui_style.COLORS["danger_red"]),
        }
        text, color = status_styles.get(
            status,
            (f"⚪ {status}", ui_style.COLORS["text_muted"]),
        )
        error = str(getattr(health, "error", "") or "").strip()
        self.sidebar_record_status.setText(text)
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 13px; color: {color}; font-weight: 600;"
        )
        if error and hasattr(self.sidebar_record_status, "setToolTip"):
            self.sidebar_record_status.setToolTip(error)
        top_status = getattr(self, "top_record_status", None)
        if top_status is not None:
            top_status.setText(text)
            kind = "success" if status == "running" else "error" if status == "fatal" else "warning" if status in {"paused", "delayed", "sample_delayed", "degraded"} else "neutral"
            top_status.set_kind(kind)
            top_status.setToolTip(error)
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
        consecutive_days = int(
            getattr(
                today_page,
                "last_recording_streak_days",
                getattr(today_page, "last_consecutive_days", 0),
            )
            or 0
        )
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
            text = "记录中"
            color = ui_style.COLORS["success_green"]
        else:
            self.worker.pause()
            self.btn_pause.setText("继续记录")
            self.btn_pause.setStyleSheet(ui_style.get_button_primary_style())
            text = "已暂停"
            color = ui_style.COLORS["warning_yellow"]

        prefix = "🟢" if self.worker.is_paused() is False else "🟡"
        self.sidebar_record_status.setText(f"{prefix} {text}")
        self.sidebar_record_status.setStyleSheet(
            f"font-size: 13px; color: {color}; font-weight: 600;"
        )
        self.top_record_status.setText(text)
        self.top_record_status.set_kind("success" if not self.worker.is_paused() else "warning")

    def _on_dashboard_snapshot(self, snapshot: DashboardSnapshot) -> None:
        if not isinstance(snapshot, DashboardSnapshot):
            return
        self.pages["today"].apply_snapshot(snapshot.payload)
        self._dashboard_snapshot = snapshot
        self.top_data_status.hide()
        self._update_top_bar()
        self._show_daily_observation()
        self._maybe_generate_daily_observation(snapshot.payload)
        day = snapshot.payload.get("today") if isinstance(snapshot.payload, dict) else None
        if isinstance(day, str):
            self._request_goal_day(day)

    def _open_day_activity(self, day: str) -> None:
        payload = getattr(self._dashboard_snapshot, "payload", {}) or {}
        dates = payload.get("rhythm", {}).get("7d", {}).get("chart", {}).get("dates", [])
        try:
            dates = [date.fromisoformat(str(value)).isoformat() for value in dates]
        except (ValueError, TypeError):
            return
        if not 1 <= len(dates) <= 7 or day not in dates:
            return
        current = self._day_activity_dialog
        if current is not None and current.isVisible():
            current_dates = [current.day_picker.itemData(i) for i in range(current.day_picker.count())]
            if current_dates == dates:
                current.day_picker.setCurrentIndex(current.day_picker.findData(day))
                current.raise_()
                current.activateWindow()
                return
            current.close()
        mapping = dict(self.display_name_mapping)
        dialog = DayActivityDialog(
            self.db_path, day, dates, parent=self,
            sample_interval=self.config.get("sample_interval", 1),
            display_resolver=lambda process, details: resolve_display_name(process, details, mapping),
        )
        self._day_activity_dialog = dialog
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.finished.connect(lambda _result, current=dialog: self._release_day_activity(current))
        dialog.show()

    def _release_day_activity(self, dialog) -> None:
        if self._day_activity_dialog is dialog:
            self._day_activity_dialog = None

    def _request_goal_day(self, day: str, *, force: bool = False) -> None:
        from ..services.daily_goal_service import load_goal_day

        now = time.monotonic()
        if (not force and day == getattr(self, "_last_goal_load_day", "")
                and now - getattr(self, "_last_goal_load_at", 0.0) < 30):
            return
        self._last_goal_load_day = day
        self._last_goal_load_at = now
        self.background_tasks.submit(
            f"goal:load:{day}",
            lambda: load_goal_day(self.db_path, self.paths.intelligence_dir, day),
        )

    def _on_dashboard_refresh_failed(self, message: str) -> None:
        print(f"[DashboardRefresh] {message}", file=sys.stderr)
        if hasattr(self, "top_data_status"):
            snapshot = getattr(self, "_dashboard_snapshot", None)
            loaded_at = getattr(snapshot, "loaded_at", None)
            suffix = time.strftime("%H:%M", time.localtime(loaded_at)) if loaded_at else "--:--"
            self.top_data_status.setText(f"读取失败 · 上次 {suffix}")
            self.top_data_status.set_kind("error")
            self.top_data_status.setToolTip(str(message))
            self.top_data_status.show()

    def _update_top_bar(self) -> None:
        if self._current_nav_key == "today":
            self.lbl_today.setText(self._today_text())
        today = datetime.now().strftime("%Y-%m-%d")
        today_page = self.pages.get("today")
        if (
            today_page is not None
            and today_page.last_stats_date == today
            and today_page.last_shell_summary
        ):
            summary = today_page.last_shell_summary
        else:
            summary = {
                "effective_seconds": 0,
                "work_seconds": 0,
                "entertainment_seconds": 0,
                "social_seconds": 0,
            }
        primary_seconds = int(summary.get("effective_seconds", 0) or 0)
        self.capsule_labels["total"].setText("有效活动")
        self.capsule_values["total"].setText(fmt_seconds(primary_seconds))
        self._update_sidebar_status_card()

    def _quick_report(self) -> None:
        job = ReportJob(
            kind="quick",
            db_path=self.db_path,
            reports_dir=self.reports_dir,
            obsidian_path=self._live_obsidian_path(),
        )
        if not self.background_tasks.submit(job.key, lambda: execute_report_job(job)):
            return
        button = getattr(self, "btn_report", None)
        if button is not None:
            button.setEnabled(False)
            button.setText("生成中…")

    def _check_report_schedule(self):
        """Periodically check if weekly/monthly reports should be auto-generated."""
        try:
            now = time.time()
            last = getattr(self, '_last_report_gen', 0)
            # Debounce repeated signals while still checking each minute.
            if now - last < 50:
                return

            job = ReportJob(
                kind="periodic",
                db_path=self.db_path,
                reports_dir=self.reports_dir,
                obsidian_path=self._live_obsidian_path(),
            )
            if self.background_tasks.submit(job.key, lambda: execute_report_job(job)):
                self._last_report_gen = now
        except Exception as e:
            import sys, traceback
            print(f"[AutoReport] Error: {e}", file=sys.stderr)
            traceback.print_exc()

    def _auto_generate_daily_report(self):
        """Refresh today's report hourly without interrupting the GUI."""
        job = ReportJob(
            kind="daily",
            db_path=self.db_path,
            reports_dir=self.reports_dir,
            obsidian_path=self._live_obsidian_path(),
        )
        self.background_tasks.submit(job.key, lambda: execute_report_job(job))

    def _start_report_backfill(self) -> None:
        job = ReportJob(
            kind="backfill",
            db_path=self.db_path,
            reports_dir=self.reports_dir,
            obsidian_path=self._live_obsidian_path(),
        )
        self.background_tasks.submit(job.key, lambda: execute_report_job(job))

    def _on_background_task_completed(self, key: str, result: object) -> None:
        import sys

        if key.startswith("goal:load:"):
            from ..services.daily_goal_service import GoalStore
            model = result if isinstance(result, dict) else {}
            day = key.removeprefix("goal:load:")
            try:
                if (model.get("status") != "unavailable"
                        and model.get("revision") != GoalStore(self.paths.intelligence_dir).load()["revision"]):
                    QTimer.singleShot(100, lambda: self._request_goal_day(day, force=True))
                    return
            except RuntimeError:
                model = {"day": day, "status": "unavailable", "goals": []}
            if day == self.pages["goals"].selected_day():
                self.pages["goals"].set_model(model)
            return

        if key.startswith("observation:"):
            self._show_daily_observation()
            return
        if key == "report:quick":
            button = getattr(self, "btn_report", None)
            if button is not None:
                button.setEnabled(True)
                button.setText("生成日报")
            data = result if isinstance(result, dict) else {}
            paths = data.get("generated_paths", [])
            path = paths[0] if paths else ""
            synced = data.get("synced_path")
            message = f"日报已保存到\n{path}"
            if synced:
                message += f"\n\n已同步到 Obsidian:\n{synced}"
            QMessageBox.information(self, "生成成功", message)
            return
        if key == "report:backfill":
            data = result if isinstance(result, dict) else {}
            summary = data.get("summary", {})
            print(
                "[AutoReport] Backfill generated "
                f"{summary.get('generated_count', 0)}, "
                f"failed {summary.get('failure_count', 0)}",
                file=sys.stderr,
            )
            return
        if key in {"report:daily", "report:periodic"}:
            data = result if isinstance(result, dict) else {}
            for filepath in data.get("generated_paths", []):
                print(f"[AutoReport] Generated: {filepath}", file=sys.stderr)

    def _on_background_task_failed(self, key: str, error: str) -> None:
        if key == "report:quick":
            button = getattr(self, "btn_report", None)
            if button is not None:
                button.setEnabled(True)
                button.setText("生成日报")
            QMessageBox.warning(self, "生成失败", error)
            return
        import sys

        print(f"[BackgroundTask] {key} failed: {error}", file=sys.stderr)

    def _live_obsidian_path(self) -> str:
        """Return obsidian_output_path from in-memory config (merged with DB on startup)."""
        return self.config.get("obsidian_output_path", "").strip()

    def _apply_saved_config(self, config: dict) -> None:
        self.config = config
        MainWindow._show_daily_observation(self)
        refresh = getattr(self, 'dashboard_refresh', None)
        invalidate = getattr(refresh, 'invalidate_context', None)
        if callable(invalidate):
            invalidate()
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

        if not MainWindow._suspend_dashboard_refresh(self):
            restart_handle.cancel()
            QMessageBox.warning(
                self,
                "重启失败",
                "首页后台查询仍在运行，请稍后重试。",
            )
            return

        result = stop_recording_worker_safely(self.worker)
        if not result.completed:
            restart_handle.cancel()
            MainWindow._resume_dashboard_refresh(self)
            QMessageBox.warning(self, "Cannot restart safely", result.message)
            return

        try:
            restart_handle.arm()
        except Exception as exc:
            restart_handle.cancel()
            try:
                self.worker = self._restore_recording_worker()
            except Exception as restore_exc:
                MainWindow._resume_dashboard_refresh(self)
                QMessageBox.warning(
                    self,
                    "记录恢复失败",
                    f"{exc}\n\n记录线程恢复失败：{restore_exc}",
                )
                return
            MainWindow._resume_dashboard_refresh(self)
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
        MainWindow._perform_safe_quit(self)

    def _check_maintenance_request(self) -> None:
        request = consume_maintenance_request(os.path.dirname(self.db_path))
        if request is not None:
            self._perform_safe_quit(request_id=request['id'])

    def _perform_safe_quit(self, request_id=None) -> None:
        if not MainWindow._suspend_dashboard_refresh(self):
            message = "首页后台查询仍在运行，请稍后重试。"
            if request_id:
                record_maintenance_result(os.path.dirname(self.db_path), request_id, 'failed', message)
            else:
                QMessageBox.warning(self, "无法安全退出", message)
            return
        result = stop_recording_worker_safely(self.worker)
        if not result.completed:
            MainWindow._resume_dashboard_refresh(self)
            if request_id:
                record_maintenance_result(os.path.dirname(self.db_path), request_id, 'failed', result.message)
            else:
                QMessageBox.warning(self, "Cannot quit safely", result.message)
            return
        if request_id:
            record_maintenance_result(os.path.dirname(self.db_path), request_id, 'completed', '')
        app = QApplication.instance()
        if app is not None:
            app.quit()

    @staticmethod
    def _suspend_dashboard_refresh(window) -> bool:
        for timer_name in ("report_schedule_timer", "daily_report_timer", "maintenance_timer"):
            timer = getattr(window, timer_name, None)
            if timer is not None:
                timer.stop()
        refresh = getattr(window, "dashboard_refresh", None)
        completed = True if refresh is None else bool(refresh.shutdown(timeout_ms=5_000))
        statistics_page = getattr(window, "pages", {}).get("stats")
        if completed and statistics_page is not None and hasattr(statistics_page, "shutdown"):
            completed = bool(statistics_page.shutdown(timeout_ms=5_000))
        tasks = getattr(window, "background_tasks", None)
        if completed and tasks is not None:
            completed = bool(tasks.shutdown(timeout_ms=5_000))
        if not completed:
            MainWindow._resume_dashboard_refresh(window)
        return completed

    @staticmethod
    def _resume_dashboard_refresh(window) -> None:
        refresh = getattr(window, "dashboard_refresh", None)
        is_visible = getattr(window, "isVisible", None)
        foreground = bool(is_visible()) if callable(is_visible) else True
        if refresh is not None:
            refresh.resume(foreground)
        statistics_page = getattr(window, "pages", {}).get("stats")
        if statistics_page is not None and hasattr(statistics_page, "resume"):
            statistics_page.resume()
        tasks = getattr(window, "background_tasks", None)
        if tasks is not None:
            tasks.resume()
        report_timer = getattr(window, "report_schedule_timer", None)
        if report_timer is not None:
            report_timer.start(60000)
        daily_timer = getattr(window, "daily_report_timer", None)
        if daily_timer is not None:
            daily_timer.start(3600000)
        maintenance_timer = getattr(window, "maintenance_timer", None)
        if maintenance_timer is not None:
            maintenance_timer.start(1000)

    def _restore_recording_worker(self):
        from .worker import RecordingWorker

        replacement = RecordingWorker(
            self.config_path,
            self.db_path,
            self.config,
            paths=self.paths,
        )
        self._connect_recording_worker(replacement)
        self._recording_health = replacement.health
        self._update_recording_health_ui()
        for page_key in ("rules", "settings"):
            page = self.pages.get(page_key)
            if page is not None and hasattr(page, "worker"):
                page.worker = replacement
                intelligence_settings = getattr(page,'intelligence_settings',None)
                if intelligence_settings is not None:
                    intelligence_settings.worker = replacement
        replacement.start()
        return replacement

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        refresh = getattr(self, "dashboard_refresh", None)
        if refresh is not None:
            refresh.set_foreground(True)

    def hideEvent(self, event) -> None:  # noqa: N802
        refresh = getattr(self, "dashboard_refresh", None)
        if refresh is not None:
            refresh.set_foreground(False)
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_responsive_top_bar()

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
