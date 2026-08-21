from __future__ import annotations

import ctypes


def test_duplicate_launch_does_not_reactivate_already_foreground_window(monkeypatch):
    from daylens.services import gui_bootstrap

    class FindWindow:
        restype = None

        def __call__(self, _class_name, _window_title):
            return 42

    class FakeUser32:
        def __init__(self):
            self.FindWindowW = FindWindow()
            self.calls = []

        def IsWindowVisible(self, hwnd):
            assert hwnd == 42
            return True

        def IsIconic(self, hwnd):
            assert hwnd == 42
            return False

        def GetForegroundWindow(self):
            return 42

        def ShowWindow(self, hwnd, command):
            self.calls.append(("show", hwnd, command))

        def SetForegroundWindow(self, hwnd):
            self.calls.append(("foreground", hwnd))

    fake_user32 = FakeUser32()
    monkeypatch.setattr(ctypes.windll, "user32", fake_user32, raising=False)

    gui_bootstrap._activate_existing_window()

    assert fake_user32.calls == []


def test_second_gui_launch_activates_existing_window(monkeypatch):
    from daylens.services import gui_bootstrap

    activated = []
    monkeypatch.setattr(
        gui_bootstrap,
        "acquire_recording_lock",
        lambda: (False, None),
    )
    monkeypatch.setattr(
        gui_bootstrap,
        "_activate_existing_window",
        lambda: activated.append(True),
    )

    is_first, handle = gui_bootstrap.ensure_single_instance()

    assert (is_first, handle) == (False, None)
    assert activated == [True]


def test_cli_recording_start_uses_the_same_recording_lock():
    from pathlib import Path

    source = Path("src/daylens/services/command_handlers.py").read_text(
        encoding="utf-8"
    )

    assert "acquire_recording_lock" in source
    assert "DayLens_RecordingInstance" in Path(
        "src/daylens/services/instance_lock.py"
    ).read_text(encoding="utf-8")
