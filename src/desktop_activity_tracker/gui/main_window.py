"""Main application window with sidebar navigation and stacked pages."""

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget, QPushButton, QMessageBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from .. import database
from ..utils import fmt_seconds

from .style import (
    COLORS, GLOBAL_STYLE, SIDEBAR_STYLE, TOP_BAR_STYLE, BOTTOM_BAR_STYLE,
    BUTTON_PRIMARY_STYLE, BUTTON_SECONDARY_STYLE, BUTTON_DANGER_STYLE,
    SECTION_TITLE, INPUT_STYLE
)
from .pages.today_overview import TodayOverviewPage
from .pages.live_monitor import LiveMonitorPage
from .pages.software_stats import SoftwareStatsPage
from .pages.category_stats import CategoryStatsPage
from .pages.reports import ReportsPage
from .pages.rule_config import RuleConfigPage
from .pages.settings import SettingsPage


NAV_ITEMS = [
    ("\U0001F4CA  今日概览", "today"),
    ("\U0001F4E1  实时监控", "live"),
    ("\U0001F4BB  软件统计", "software"),
    ("\U0001F4CA  分类统计", "category"),
    ("\U0001F4C4  日报/周报", "reports"),
    ("⚙️  规则配置", "rules"),
    ("\U0001F527  设置", "settings"),
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
        self.resize(960, 700)
        self.setMinimumSize(860, 580)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top bar ──
        root_layout.addWidget(self._build_top_bar())

        # ── Main content ──
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self._build_sidebar())
        content.addWidget(self._build_pages(), 1)
        root_layout.addLayout(content, 1)

        # ── Bottom bar ──
        root_layout.addWidget(self._build_bottom_bar())

        self.worker.sample_updated.connect(self._on_sample)
        self.nav_list.setCurrentRow(0)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_top_bar)
        self.refresh_timer.start(30000)

    def _build_sidebar(self):
        frame = QFrame()
        frame.setFixedWidth(210)
        frame.setStyleSheet(f"background: {COLORS['sidebar_bg']};")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(0)

        # Brand / logo area
        brand = QLabel("Activity\nTracker")
        brand.setStyleSheet(f"""
            font-size: 16px; font-weight: 800; color: {COLORS['text_inverse']};
            padding: 12px 20px 20px 20px;
        """)
        layout.addWidget(brand)

        # Divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background: {COLORS['sidebar_hover']}; margin: 0 12px;")
        layout.addWidget(div)

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

        # Version label
        ver = QLabel("v1.2.0")
        ver.setStyleSheet(f"font-size: 10px; color: {COLORS['text_muted']}; padding: 8px 16px;")
        layout.addWidget(ver)

        return frame

    def _build_pages(self):
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
        return self.stack

    # ── Top bar ──────────────────────────────────────────────────────

    def _build_top_bar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setStyleSheet(TOP_BAR_STYLE)
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)

        title = QLabel("今日概览")
        title.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {COLORS['text']};")
        self.lbl_page_title = title
        layout.addWidget(title)

        self.top_summary = QLabel()
        self.top_summary.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']};")
        self._update_top_bar()
        layout.addWidget(self.top_summary)
        layout.addStretch()

        self.btn_pause = QPushButton("⏸  暂停")
        self.btn_pause.setStyleSheet(BUTTON_SECONDARY_STYLE)
        self.btn_pause.setCursor(Qt.PointingHandCursor)
        self.btn_pause.clicked.connect(self._toggle_pause)
        layout.addWidget(self.btn_pause)

        btn_report = QPushButton("\U0001F4C4  生成日报")
        btn_report.setStyleSheet(BUTTON_PRIMARY_STYLE)
        btn_report.setCursor(Qt.PointingHandCursor)
        btn_report.clicked.connect(self._quick_report)
        layout.addWidget(btn_report)
        return bar

    # ── Bottom bar ───────────────────────────────────────────────────

    def _build_bottom_bar(self):
        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar.setStyleSheet(BOTTOM_BAR_STYLE)
        bar.setFixedHeight(32)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)

        # Status indicator dot + text
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(
            f"background: {COLORS['success_green']}; border-radius: 4px;"
        )
        self._status_dot = dot
        layout.addWidget(dot)

        self.lbl_status = QLabel("记录中")
        self.lbl_status.setStyleSheet(
            f"font-size: 12px; color: {COLORS['success_green']}; font-weight: 600;"
        )
        layout.addWidget(self.lbl_status)
        layout.addSpacing(20)

        self.lbl_time = QLabel()
        self.lbl_time.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(self.lbl_time)
        layout.addStretch()

        btn_quit = QPushButton("退出程序")
        btn_quit.setStyleSheet(BUTTON_DANGER_STYLE)
        btn_quit.setCursor(Qt.PointingHandCursor)
        btn_quit.clicked.connect(self._quit_app)
        layout.addWidget(btn_quit)
        return bar

    # ── Navigation ───────────────────────────────────────────────────

    def _on_nav_changed(self, row):
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)
            name = NAV_ITEMS[row][0]
            # Strip emoji prefix
            clean = name.split('  ')[-1] if '  ' in name else name
            self.lbl_page_title.setText(clean)

    def _on_sample(self, sample):
        if self.stack.currentWidget() is self.pages.get('live'):
            self.pages['live'].on_sample_updated(sample)
        self.lbl_time.setText(
            f"\U0001F552 {datetime.now().strftime('%H:%M:%S')}"
        )

    # ── Pause / Resume ───────────────────────────────────────────────

    def _toggle_pause(self):
        if self.worker.is_paused():
            self.worker.resume()
            self.btn_pause.setText("⏸  暂停")
            self.btn_pause.setStyleSheet(BUTTON_SECONDARY_STYLE)
            self.lbl_status.setText("记录中")
            self.lbl_status.setStyleSheet(
                f"font-size: 12px; color: {COLORS['success_green']}; font-weight: 600;"
            )
            self._status_dot.setStyleSheet(
                f"background: {COLORS['success_green']}; border-radius: 4px;"
            )
        else:
            self.worker.pause()
            self.btn_pause.setText("▶  恢复")
            self.btn_pause.setStyleSheet(BUTTON_PRIMARY_STYLE)
            self.lbl_status.setText("已暂停")
            self.lbl_status.setStyleSheet(
                f"font-size: 12px; color: {COLORS['warning_yellow']}; font-weight: 600;"
            )
            self._status_dot.setStyleSheet(
                f"background: {COLORS['warning_yellow']}; border-radius: 4px;"
            )

    # ── Top stats ────────────────────────────────────────────────────

    def _update_top_bar(self):
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            totals = stats.get('totals', {})
            effective = totals.get('effective_seconds', 0) or 0
            work_cats = {"ai_tools", "coding", "reading", "creative"}
            work_sec = sum(c.get('effective_seconds', 0) or 0 for c in stats.get('by_category', [])
                          if c.get('category_key') in work_cats)
            video_sec = sum(c.get('effective_seconds', 0) or 0 for c in stats.get('by_category', [])
                           if c.get('category_key') in ('video', 'gaming'))
            self.top_summary.setText(
                f"\U0001F3AF {fmt_seconds(effective)}  |  "
                f"\U0001F4AA {fmt_seconds(work_sec)}  |  "
                f"\U0001F3AE {fmt_seconds(video_sec)}"
            )
        except Exception as e:
            import sys, traceback
            print(f"[MainWindow] _update_top_bar error: {e}", file=sys.stderr)
            traceback.print_exc()

    # ── Quick report ─────────────────────────────────────────────────

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

    # ── Quit ─────────────────────────────────────────────────────────

    def _quit_app(self):
        reply = QMessageBox.question(
            self, "确认退出", "确定要退出程序吗？\n系统托盘图标也会关闭。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        if self.worker:
            self.worker.stop()
            self.worker.wait(3000)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    # ── Close → tray ─────────────────────────────────────────────────

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if hasattr(self, 'tray'):
            self.tray.showMessage(
                "Desktop Activity Tracker",
                "程序已最小化到系统托盘\n"
                + "右键点击右侧托盘图标可打开菜单\n"
                + "如未显示，请点击 ^ 箭头"
            )
