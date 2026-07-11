from __future__ import annotations

import os
from types import SimpleNamespace

from PySide6.QtWidgets import QSystemTrayIcon

from daylens.gui import tray_manager
from daylens.gui.tray_manager import TrayManager


def test_tray_manager_stores_injected_report_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)

    manager = TrayManager(None, "usage.db", {}, str(tmp_path / "reports"))

    assert manager.reports_dir == str(tmp_path / "reports")


def test_tray_report_actions_use_injected_report_directory(tmp_path, monkeypatch):
    reports_dir = str(tmp_path / "reports")
    calls = []
    opened = []
    manager = TrayManager.__new__(TrayManager)
    manager.db_path = "usage.db"
    manager.reports_dir = reports_dir
    manager.config = {"obsidian_output_path": "E:/vault"}
    manager.tray = SimpleNamespace(showMessage=lambda *args: None)
    monkeypatch.setattr(
        tray_manager,
        "generate_daily_report",
        lambda db, directory, obsidian: calls.append((db, directory, obsidian)),
    )
    monkeypatch.setattr(os, "startfile", opened.append)

    manager._auto_generate_report()
    manager._generate_report()
    manager._open_reports()

    expected_daily = os.path.join(reports_dir, "daily")
    assert calls == [
        ("usage.db", expected_daily, "E:/vault"),
        ("usage.db", expected_daily, "E:/vault"),
    ]
    assert opened == [reports_dir]
