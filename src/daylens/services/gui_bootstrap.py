"""GUI bootstrap helpers split from the legacy main entrypoint."""

from __future__ import annotations

import os
import sys

from .. import get_app_root
from ..runtime import ensure_report_subdirs, load_config, resolve_config_path
from .bootstrap_runtime_service import (
    load_bootstrap_state,
    prepare_runtime_config,
    refresh_custom_rules,
    shutdown_runtime_state,
)
from .rules_service import save_scanned_rules


def auto_scan_and_save_rules(config: dict, db_path: str) -> None:
    try:
        from daylens.app_scanner import _scan_registry_uninstall, classify_scanned_apps

        apps = _scan_registry_uninstall()
        classified = classify_scanned_apps(apps)
    except Exception:
        return

    saved_count = save_scanned_rules(db_path, config, classified)
    if saved_count:
        print(f"[INFO] 首次运行，已自动分类 {saved_count} 个应用")


def ensure_single_instance() -> tuple[bool, object | None]:
    import atexit
    import ctypes
    from ctypes import wintypes

    mutex_name = "Global\\DayLens_SingleInstance"
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE

    handle = kernel32.CreateMutexW(None, True, mutex_name)
    if kernel32.GetLastError() == 183:
        if handle:
            kernel32.CloseHandle(handle)
        ctypes.windll.user32.MessageBoxW(0, "程序已在运行中，请查看系统托盘图标。", "DayLens", 0x40)
        return False, None
    atexit.register(kernel32.CloseHandle, handle)
    return True, handle


def launch_gui() -> None:
    is_first, _mutex = ensure_single_instance()
    if not is_first:
        sys.exit(0)

    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from ..gui.main_window import MainWindow
    from ..gui.tray_manager import TrayManager
    from ..gui.worker import RecordingWorker

    config_path = resolve_config_path()
    config = load_config(config_path)
    config, db_path = prepare_runtime_config(config)

    # Resolve reports_dir from the persistent data directory (alongside DB)
    reports_dir = os.path.join(os.path.dirname(db_path), "reports")
    ensure_report_subdirs(reports_dir)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei", 10))

    settings, existing_rules = load_bootstrap_state(db_path)
    if settings.get("wizard_completed") != "true":
        if not existing_rules:
            auto_scan_and_save_rules(config, db_path)
            refresh_custom_rules(config, db_path)
        from ..gui.wizard import SetupWizard

        wizard = SetupWizard(config_path, db_path)
        wizard.exec()
        refresh_custom_rules(config, db_path)

    worker = RecordingWorker(config_path, db_path, config)
    worker.start()

    tray = TrayManager(app, db_path, config)
    window = MainWindow(get_app_root(), config, db_path, config_path, reports_dir, worker)
    window.tray = tray
    tray.set_main_window(window)
    window.show()

    exit_code = app.exec()
    worker.stop()
    worker.wait(5000)
    shutdown_runtime_state()
    sys.exit(exit_code)
