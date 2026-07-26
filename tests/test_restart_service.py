from __future__ import annotations

import subprocess

from daylens.services.restart_service import database_path_changed, schedule_restart


class RecordingStdin:
    def __init__(self):
        self.value = ""
        self.closed = False

    def write(self, value):
        self.value += value

    def flush(self):
        return None

    def close(self):
        self.closed = True


def test_database_path_changed_ignores_equivalent_windows_paths():
    assert database_path_changed(r"D:\Data\usage.db", "d:/data/usage.db") is False
    assert database_path_changed(r"D:\Data\usage.db", r"D:\Other\usage.db") is True


def test_schedule_restart_starts_hidden_waiter(monkeypatch):
    captured = {}
    stdin = RecordingStdin()
    process = type("Process", (), {"stdin": stdin})()

    def fake_popen(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    schedule_restart([r"D:\OfficeSoftware\DayLens\release\DayLens.exe"], current_pid=123)

    assert captured["args"][:4] == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-WindowStyle",
    ]
    assert captured["kwargs"]["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert stdin.value == "ARM\n"
    assert stdin.closed is True


def test_deferred_restart_waiter_launches_only_after_arm(monkeypatch):
    captured = {}
    stdin = RecordingStdin()
    process = type("Process", (), {"stdin": stdin})()

    def fake_popen(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return process

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    handle = schedule_restart(
        [r"D:\OfficeSoftware\DayLens\release\DayLens.exe"],
        current_pid=123,
        deferred=True,
    )

    assert stdin.value == ""
    assert "ReadLine" in captured["args"][-1]

    handle.arm()

    assert stdin.value == "ARM\n"
    assert stdin.closed is True


def test_deferred_restart_waiter_can_be_cancelled(monkeypatch):
    stdin = RecordingStdin()
    process = type("Process", (), {"stdin": stdin})()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    handle = schedule_restart(
        [r"D:\OfficeSoftware\DayLens\release\DayLens.exe"],
        current_pid=123,
        deferred=True,
    )
    handle.cancel()

    assert stdin.value == "CANCEL\n"
    assert stdin.closed is True
