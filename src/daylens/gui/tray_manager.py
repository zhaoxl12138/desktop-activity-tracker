"""System tray icon and popup menu for DayLens."""

from __future__ import annotations

import os
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import database, get_app_root, get_data_dir
from ..gui import style as ui_style
from ..utils import fmt_seconds


class TrayManager:
    def __init__(self, app, db_path, config):
        self.app = app
        self.db_path = db_path
        self.config = config
        self.main_window = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("[TrayManager] 系统托盘不可用，跳过托盘创建。")
            self.tray = None
            return

        if getattr(sys, "frozen", False):
            base = sys._MEIPASS
        else:
            base = get_app_root()

        icon = None
        for path in [os.path.join(base, "assets", "icon.ico"), os.path.join(base, "icon.ico")]:
            if os.path.exists(path):
                icon = QIcon(path)
                break

        if icon:
            app.setWindowIcon(icon)

        self.tray = QSystemTrayIcon(
            icon or app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        )
        self.tray.setToolTip("DayLens\n启动中...")
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self.tooltip_timer = QTimer(self.tray)
        self.tooltip_timer.timeout.connect(self._update_tooltip)
        self.tooltip_timer.start(60000)
        self._update_tooltip()

        self.report_timer = QTimer(self.tray)
        self.report_timer.timeout.connect(self._auto_generate_report)
        self.report_timer.start(300000)
        self._auto_generate_report()

    def set_main_window(self, window) -> None:
        self.main_window = window

    def _show_tray_popup(self) -> None:
        popup = QWidget()
        popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        C = ui_style.COLORS
        popup.setStyleSheet(f"""
            QWidget {{
                background: {C['panel_bg_alt']};
                border: 1px solid {C['border_light']};
                border-radius: 10px;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                padding: 8px 28px 8px 14px;
                text-align: left;
                font-size: 13px;
                color: {C['text_secondary']};
            }}
            QPushButton:hover {{
                background: {C['sidebar_hover']};
                color: {C['text']};
                border-radius: 4px;
            }}
            QPushButton#btnQuit {{
                color: {C['danger_red']};
                font-weight: 600;
            }}
            QPushButton#btnQuit:hover {{
                background: {C['danger_bg']};
                color: {C['danger_red']};
            }}
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

        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background: {ui_style.COLORS['border_light']}; margin: 2px 8px;")
        layout.addWidget(separator)

        btn_quit = QPushButton("退出程序")
        btn_quit.setObjectName("btnQuit")
        btn_quit.setCursor(Qt.PointingHandCursor)
        btn_quit.clicked.connect(lambda: (popup.close(), self._quit()))
        layout.addWidget(btn_quit)

        popup.adjustSize()

        cursor_pos = QCursor.pos()
        screen = QApplication.primaryScreen().availableGeometry()
        x = cursor_pos.x()
        y = cursor_pos.y() - popup.height() - 8
        if x + popup.width() > screen.right():
            x = screen.right() - popup.width() - 4
        if x < screen.left():
            x = screen.left() + 4
        if y < screen.top():
            y = cursor_pos.y() + 20

        popup.move(x, y)
        popup.setAttribute(Qt.WA_DeleteOnClose)
        popup.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Context:
            self._show_tray_popup()
        elif reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._open_window()

    def _open_window(self) -> None:
        if self.main_window:
            if self.main_window.isMinimized():
                self.main_window.showNormal()
            else:
                self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()

    def _toggle_pause(self) -> None:
        if not self.main_window or not hasattr(self.main_window, "worker"):
            return
        worker = self.main_window.worker
        if worker.is_paused():
            worker.resume()
        else:
            worker.pause()

    def _auto_generate_report(self) -> None:
        """Silent auto-generation every 5 minutes; overwrites today's report."""
        today = datetime.now().strftime("%Y-%m-%d")
        reports_dir = os.path.join(get_data_dir(), "reports", "daily")
        os.makedirs(reports_dir, exist_ok=True)
        from .. import exporter as exporter

        try:
            exporter.export_markdown(self.db_path, today, reports_dir)
            obsidian_path = self.config.get("obsidian_output_path", "").strip()
            if obsidian_path:
                markdown_file = os.path.join(reports_dir, f"{today}.md")
                exporter.sync_to_obsidian(markdown_file, obsidian_path)
        except Exception as e:
            print(f"[TrayManager] auto_generate_report error: {e}", file=sys.stderr)

    def _generate_report(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        reports_dir = os.path.join(get_data_dir(), "reports", "daily")
        os.makedirs(reports_dir, exist_ok=True)
        from .. import exporter as exporter

        try:
            exporter.export_markdown(self.db_path, today, reports_dir)
            obsidian_path = self.config.get("obsidian_output_path", "").strip()
            if obsidian_path:
                markdown_file = os.path.join(reports_dir, f"{today}.md")
                exporter.sync_to_obsidian(markdown_file, obsidian_path)
            self.tray.showMessage("DayLens", f"日报已生成\n{today}.md")
        except Exception as exc:
            self.tray.showMessage("DayLens", f"生成失败: {exc}")

    def _open_reports(self) -> None:
        reports_dir = os.path.join(get_data_dir(), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        os.startfile(reports_dir)

    def _quit(self) -> None:
        if self.main_window and hasattr(self.main_window, "worker"):
            self.main_window.worker.stop()
            self.main_window.worker.wait(5000)
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()

    def _update_tooltip(self) -> None:
        if self.tray is None:
            return
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            stats = database.query_date_stats(self.db_path, today)
            totals = stats.get("totals", {})
            effective = totals.get("effective_seconds", 0) or 0
            work_categories = {"ai_tools", "coding", "reading", "creative"}
            work_seconds = sum(
                item.get("effective_seconds", 0) or 0
                for item in stats.get("by_category", [])
                if item.get("category_key") in work_categories
            )
            video_seconds = sum(
                item.get("effective_seconds", 0) or 0
                for item in stats.get("by_category", [])
                if item.get("category_key") == "video"
            )
            status = "记录中"
            if (
                self.main_window
                and hasattr(self.main_window, "worker")
                and self.main_window.worker.is_paused()
            ):
                status = "已暂停"

            tooltip = (
                f"DayLens\n"
                f"今日有效: {fmt_seconds(effective)}\n"
                f"办公: {fmt_seconds(work_seconds)}\n"
                f"娱乐: {fmt_seconds(video_seconds)}\n"
                f"状态: {status}"
            )
            self.tray.setToolTip(tooltip)
        except Exception as exc:
            print(f"[TrayManager] _update_tooltip error: {exc}", file=sys.stderr)
