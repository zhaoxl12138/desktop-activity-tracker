"""System tray icon and menu for Desktop Activity Tracker."""

import os
import sys
from datetime import datetime

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QStyle, QApplication
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QTimer

from .. import database, get_app_root
from ..utils import fmt_seconds


class TrayManager:
    def __init__(self, app, db_path, config):
        self.app = app
        self.db_path = db_path
        self.config = config
        self.main_window = None

        # Try to load an icon, fallback to system default
        icon_paths = [
            os.path.join(get_app_root(), "assets", "icon.ico"),
            os.path.join(get_app_root(), "icon.ico"),
        ]
        icon = None
        for p in icon_paths:
            if os.path.exists(p):
                icon = QIcon(p)
                break

        self.tray = QSystemTrayIcon(icon or app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.tray.setToolTip("Desktop Activity Tracker\n启动中...")

        self._build_menu()
        self.tray.show()

        # Update tooltip every 60s
        self.tooltip_timer = QTimer()
        self.tooltip_timer.timeout.connect(self._update_tooltip)
        self.tooltip_timer.start(60000)
        self._update_tooltip()

    def set_main_window(self, window):
        self.main_window = window

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 4px;
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 8px 32px 8px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: #EFF6FF;
                color: #1E40AF;
            }}
            QMenu::separator {{
                height: 1px;
                background: #E2E8F0;
                margin: 4px 8px;
            }}
        """)

        self.action_open = QAction("打开主界面")
        self.action_open.triggered.connect(self._open_window)
        menu.addAction(self.action_open)

        menu.addSeparator()

        self.action_pause = QAction("暂停记录")
        self.action_pause.triggered.connect(self._toggle_pause)
        menu.addAction(self.action_pause)

        self.action_report = QAction("生成今日日报")
        self.action_report.triggered.connect(self._generate_report)
        menu.addAction(self.action_report)

        self.action_open_reports = QAction("打开报告目录")
        self.action_open_reports.triggered.connect(self._open_reports)
        menu.addAction(self.action_open_reports)

        menu.addSeparator()

        action_settings = QAction("设置")
        action_settings.triggered.connect(self._open_window)
        menu.addAction(action_settings)

        menu.addSeparator()

        action_quit = QAction("退出程序")
        action_quit.triggered.connect(self._quit)
        menu.addAction(action_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        # Left-click or double-click → open main window
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._open_window()
        # Right-click → shows context menu automatically with 退出程序

    def _open_window(self):
        if self.main_window:
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()

    def _toggle_pause(self):
        if self.main_window and hasattr(self.main_window, 'worker'):
            w = self.main_window.worker
            if w.is_paused():
                w.resume()
                self.action_pause.setText("暂停记录")
            else:
                w.pause()
                self.action_pause.setText("恢复记录")

    def _generate_report(self):
        today = datetime.now().strftime("%Y-%m-%d")
        reports_dir = os.path.join(get_app_root(), "reports", "daily")
        os.makedirs(reports_dir, exist_ok=True)
        from .. import exporter as exp
        try:
            exp.export_markdown(self.db_path, today, reports_dir)
            obsidian_path = self.config.get("obsidian_output_path", "").strip()
            if obsidian_path:
                md_file = os.path.join(reports_dir, f"{today}.md")
                exp.sync_to_obsidian(md_file, obsidian_path)
            self.tray.showMessage("Desktop Activity Tracker", f"日报已生成\n{today}.md")
        except Exception as e:
            self.tray.showMessage("Desktop Activity Tracker", f"生成失败: {e}")

    def _open_reports(self):
        reports_dir = os.path.join(get_app_root(), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        os.startfile(reports_dir)

    def _quit(self):
        if self.main_window and hasattr(self.main_window, 'worker'):
            self.main_window.worker.stop()
            self.main_window.worker.wait(5000)
        self.tray.hide()
        self.app.quit()

    def _update_tooltip(self):
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            stats = database.query_date_stats(self.db_path, today)
            totals = stats.get('totals', {})
            effective = totals.get('effective_seconds', 0) or 0
            work_cats = {"ai_tools", "coding", "reading", "creative"}
            work_sec = sum(c.get('effective_seconds', 0) or 0 for c in stats.get('by_category', [])
                          if c.get('category_key') in work_cats)
            video_sec = sum(c.get('effective_seconds', 0) or 0 for c in stats.get('by_category', [])
                           if c.get('category_key') in ('video', 'gaming'))
            status = "记录中"
            if self.main_window and hasattr(self.main_window, 'worker') and self.main_window.worker.is_paused():
                status = "已暂停"
            tooltip = (
                f"Desktop Activity Tracker\n"
                f"今日有效: {fmt_seconds(effective)}\n"
                f"学习/工作: {fmt_seconds(work_sec)}\n"
                f"娱乐: {fmt_seconds(video_sec)}\n"
                f"状态: {status}"
            )
            self.tray.setToolTip(tooltip)
        except Exception as e:
            import sys, traceback
            print(f"[TrayManager] _update_tooltip error: {e}", file=sys.stderr)
            traceback.print_exc()
