from __future__ import annotations

import subprocess

from daylens.services.restart_service import database_path_changed, schedule_restart


def test_database_path_changed_ignores_equivalent_windows_paths():
    assert database_path_changed(r"D:\Data\usage.db", "d:/data/usage.db") is False
    assert database_path_changed(r"D:\Data\usage.db", r"D:\Other\usage.db") is True


def test_schedule_restart_starts_hidden_waiter(monkeypatch):
    captured = {}

    def fake_popen(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    schedule_restart([r"D:\OfficeSoftware\DayLens\release\DayLens.exe"], current_pid=123)

    assert captured["args"][:4] == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-WindowStyle",
    ]
    assert captured["kwargs"]["creationflags"] == subprocess.CREATE_NO_WINDOW
