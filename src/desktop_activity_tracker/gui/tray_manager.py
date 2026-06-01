"""System tray icon and menu for Desktop Activity Tracker."""

import os
import sys
from datetime import datetime

from PySide6.QtWidgets import (
    QSystemTrayIcon, QMenu, QStyle, QApplication,
    QWidget, QVBoxLayout, QPushButton,
)
from PySide6.QtGui import QIcon, QAction, QCursor
from PySide6.QtCore import Qt, QTimer

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
        # Don't use setContextMenu / QMenu — unreliable on some Windows versions.
        # Instead use a frameless QWidget popup triggered on right-click.
        self.tray.activated.connect(self._on_tray_activated)

    def _show_tray_popup(self):
        popup = QWidget()
        popup.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        popup.setAttribute(Qt.WA_ShowWithoutActivating)
        popup.setStyleSheet("""
            QWidget {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
            }
            QPushButton {
                background: transparent;
                border: none;
                padding: 8px 28px 8px 14px;
                text-align: left;
                font-size: 13px;
                color: #1E293B;
            }
            QPushButton:hover {
                background: #EFF6FF;
                color: #1E40AF;
                border-radius: 4px;
            }
            QPushButton#btnQuit {
                color: #DC2626;
                font-weight: 600;
            }
            QPushButton#btnQuit:hover {
                background: #FEF2F2;
                color: #B91C1C;
            }
        """)

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        btn_open = QPushButton("打开主界面")
        btn_open.setCursor(Qt.PointingHandCursor)
        btn_open.clicked.connect(lambda: (popup.close(), self._open_window()))
        layout.addWidget(btn_open)

        btn_pause = QPushButton("暂停记录")
        btn_pause.setCursor(Qt.PointingHandCursor)
        btn_pause.clicked.connect(lambda: (popup.close(), self._toggle_pause()))
        layout.addWidget(btn_pause)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #E2E8F0; margin: 2px 8px;")
        layout.addWidget(sep)

        btn_quit = QPushButton("退出程序")
        btn_quit.setObjectName("btnQuit")
        btn_quit.setCursor(Qt.PointingHandCursor)
        btn_quit.clicked.connect(lambda: (popup.close(), self._quit()))
        layout.addWidget(btn_quit)

        popup.adjustSize()

        # Position popup ABOVE the tray icon (near bottom of screen)
        cursor_pos = QCursor.pos()
        screen = QApplication.primaryScreen().availableGeometry()
        x = cursor_pos.x()
        y = cursor_pos.y() - popup.height() - 8  # 8px gap above cursor

        # Keep within screen bounds
        if x + popup.width() > screen.right():
            x = screen.right() - popup.width() - 4
        if x < screen.left():
            x = screen.left() + 4
        if y < screen.top():
            y = cursor_pos.y() + 20  # Fallback: show below cursor

        popup.move(x, y)
        popup.show()

        # Close popup when clicking anywhere else
        QApplication.instance().focusChanged.connect(
            lambda old, new: popup.close() if popup.isVisible() and new != popup else None
        )

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Context:
            self._show_tray_popup()
        elif reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._open_window()

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
            else:
                w.pause()

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
