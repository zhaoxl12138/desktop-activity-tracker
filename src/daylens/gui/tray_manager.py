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

from .. import get_app_root
from ..gui import style as ui_style
from ..services.shell_service import build_tray_tooltip, generate_daily_report
from ..services.gui_shutdown_service import stop_recording_worker_safely


class TrayManager:
    def __init__(self, app, db_path, config, reports_dir):
        self.app = app
        self.db_path = db_path
        self.config = config
        self.reports_dir = reports_dir
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

        # 报告由主窗口统一调度。托盘只负责展示状态和手动操作，
        # 避免和主窗口同时生成同一份报告、重复读库和写文件。

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
        """兼容旧调用入口；仅在显式调用时生成，不再由定时器触发。"""
        reports_dir = os.path.join(self.reports_dir, "daily")
        try:
            generate_daily_report(
                self.db_path,
                reports_dir,
                self.config.get("obsidian_output_path", "").strip(),
            )
        except Exception as e:
            print(f"[TrayManager] auto_generate_report error: {e}", file=sys.stderr)

    def _generate_report(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        reports_dir = os.path.join(self.reports_dir, "daily")
        try:
            generate_daily_report(
                self.db_path,
                reports_dir,
                self.config.get("obsidian_output_path", "").strip(),
            )
            self.tray.showMessage("DayLens", f"日报已生成\n{today}.md")
        except Exception as exc:
            self.tray.showMessage("DayLens", f"生成失败: {exc}")

    def _open_reports(self) -> None:
        reports_dir = self.reports_dir
        os.makedirs(reports_dir, exist_ok=True)
        os.startfile(reports_dir)

    def _quit(self) -> None:
        from .main_window import MainWindow

        if (
            self.main_window is not None
            and not MainWindow._suspend_dashboard_refresh(self.main_window)
        ):
            if self.tray is not None:
                self.tray.showMessage(
                    "DayLens",
                    "首页后台查询仍在运行，请稍后重试。",
                )
            return
        worker = (
            self.main_window.worker
            if self.main_window and hasattr(self.main_window, "worker")
            else None
        )
        result = stop_recording_worker_safely(worker)
        if not result.completed:
            if self.main_window is not None:
                MainWindow._resume_dashboard_refresh(self.main_window)
            if self.tray is not None:
                self.tray.showMessage("DayLens", result.message)
            return
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()

    def _update_tooltip(self) -> None:
        if self.tray is None:
            return
        try:
            tooltip = build_tray_tooltip(
                self.db_path,
                bool(
                    self.main_window
                    and hasattr(self.main_window, "worker")
                    and self.main_window.worker.is_paused()
                ),
            )
            self.tray.setToolTip(tooltip)
        except Exception as exc:
            print(f"[TrayManager] _update_tooltip error: {exc}", file=sys.stderr)
