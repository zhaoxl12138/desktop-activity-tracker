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
from .gui_shutdown_service import (
    WorkerShutdownResult,
    stop_recording_worker_safely,
)
from .instance_lock import acquire_recording_lock


DUPLICATE_INSTANCE_MESSAGE = "程序已在运行中，请查看系统托盘图标。"


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


def _activate_existing_window() -> None:
    """Bring the existing DayLens window to the foreground on duplicate launch."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = wintypes.HWND
    hwnd = user32.FindWindowW(None, "DayLens")
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
    else:
        user32.MessageBoxW(0, DUPLICATE_INSTANCE_MESSAGE, "DayLens", 0x40)


def ensure_single_instance() -> tuple[bool, object | None]:
    acquired, lock = acquire_recording_lock()
    if not acquired:
        _activate_existing_window()
        return False, None
    return True, lock


def shutdown_gui_runtime(worker: object | None) -> WorkerShutdownResult:
    """Close shared runtime state only after the recording thread is done."""

    result = stop_recording_worker_safely(worker)
    if result.completed:
        shutdown_runtime_state()
    return result


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

    tray = TrayManager(app, db_path, config, reports_dir)
    window = MainWindow(get_app_root(), config, db_path, config_path, reports_dir, worker)
    window.tray = tray
    tray.set_main_window(window)
    window.show()

    while True:
        exit_code = app.exec()
        shutdown_result = shutdown_gui_runtime(window.worker)
        if shutdown_result.completed:
            break
        print(f"[Shutdown] {shutdown_result.message}", file=sys.stderr)
        window.show()
    sys.exit(exit_code)
